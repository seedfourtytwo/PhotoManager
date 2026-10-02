"""SQLite implementation of the Repository port (the migration runner and the shared
connections live in ``sqlite_database``; ``open_database`` is re-exported here)."""

import json
import sqlite3
import uuid
from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from pathlib import Path

from photo_assistant.adapters.sqlite_access import AccessMixin
from photo_assistant.adapters.sqlite_accounts import AccountsMixin
from photo_assistant.adapters.sqlite_albums import AlbumsMixin
from photo_assistant.adapters.sqlite_base import (
    SqliteBase,
    asset_from_row,
    decode_cursor,
    encode_cursor,
)
from photo_assistant.adapters.sqlite_database import Database, open_database
from photo_assistant.adapters.sqlite_database import migrations as _migrations
from photo_assistant.adapters.sqlite_edits import EditsMixin
from photo_assistant.adapters.sqlite_enrich import EnrichMixin
from photo_assistant.adapters.sqlite_library import LibraryMixin
from photo_assistant.adapters.sqlite_trash import TrashMixin
from photo_assistant.domain.access import SourceAccess, default_source_access
from photo_assistant.domain.model import (
    Asset,
    ImportReport,
    ItemResult,
    NewAsset,
    Outcome,
    RunStatus,
    Source,
)
from photo_assistant.ports import DuplicateAssetError, Fingerprint, Job, Page, RenderedImage

__all__ = ["Database", "DuplicateAssetError", "SqliteRepository", "_migrations", "open_database"]


def _iso(value: datetime) -> str:
    return value.isoformat()


class SqliteRepository(
    AccountsMixin,
    AccessMixin,
    LibraryMixin,
    AlbumsMixin,
    EditsMixin,
    EnrichMixin,
    TrashMixin,
    SqliteBase,
):
    """Thread-safe: writes share the process's one writer and lock, reads use per-thread
    WAL readers (``sqlite_database.Database``)."""

    def restore_from(self, snapshot: Path) -> None:
        """Replace the whole library database with a snapshot, in place (test mode only: the
        E2E suite resets the real server between tests). Other connections see it at once."""
        source = sqlite3.connect(snapshot)
        try:
            with self._lock:
                source.backup(self._conn)
        finally:
            source.close()

    def optimize(self) -> None:
        """``PRAGMA optimize``: refresh the planner's statistics where they went stale (cheap;
        the server runs it periodically, C25)."""
        with self._lock:
            self._conn.execute("PRAGMA optimize")

    # --- sources ---------------------------------------------------------------------------

    @staticmethod
    def _source(row: sqlite3.Row) -> Source:
        return Source(
            row["id"],
            row["label"],
            row["root"],
            bool(row["enabled"]),
            row["kind"],
            row["owner_id"],
        )

    def add_source(
        self,
        label: str,
        root: str | Callable[[int], str],
        owner_id: int | None = None,
        *,
        kind: str = "folder",
        access: SourceAccess | None = None,
        config: Mapping[str, object] | None = None,
    ) -> Source:
        """THE way to create a source of any kind (B17), in one transaction (or the caller's).

        ``root`` may depend on the new id (remote sources pull into ``staging/<id>``);
        ``access`` defaults to the domain rule for the kind (``default_source_access``)."""
        grants = access or default_source_access(kind, owner_id)
        try:
            with self._transaction():
                placeholder = root if isinstance(root, str) else f"pending:{uuid.uuid4().hex}"
                source_id = self._write(
                    """INSERT INTO source (kind, label, root, owner_id, config_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (kind, label, placeholder, owner_id, json.dumps(config) if config else None),
                )
                if not isinstance(root, str):
                    self._write(
                        "UPDATE source SET root = ? WHERE id = ?", (root(source_id), source_id)
                    )
                self._grant(source_id, grants)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"folder is already a source: {placeholder}") from exc
        source = self.get_source(source_id)
        assert source is not None
        return source

    def get_source(self, source_id: int) -> Source | None:
        row = self._one("SELECT * FROM source WHERE id = ?", (source_id,))
        return self._source(row) if row else None

    def list_sources(self) -> list[Source]:
        return [self._source(r) for r in self._all("SELECT * FROM source ORDER BY id")]

    def set_source_enabled(self, source_id: int, enabled: bool) -> None:
        self._write("UPDATE source SET enabled = ? WHERE id = ?", (int(enabled), source_id))

    # --- assets ----------------------------------------------------------------------------

    _asset = staticmethod(asset_from_row)

    def find_asset_id_by_hash(self, content_hash: str) -> int | None:
        row = self._one("SELECT id FROM asset WHERE content_hash = ?", (content_hash,))
        return int(row["id"]) if row else None

    def add_asset(self, asset: NewAsset, imported_at: datetime) -> int:
        try:
            return self._insert_asset(asset, imported_at)
        except sqlite3.IntegrityError as exc:
            existing = self.find_asset_id_by_hash(asset.content_hash)
            if existing is None:
                raise
            raise DuplicateAssetError(existing) from exc

    def record_import(
        self,
        asset: NewAsset,
        imported_at: datetime,
        source_id: int,
        relative_path: str,
        thumb: RenderedImage,
        job_kind: str,
        fingerprint: Fingerprint | None = None,
    ) -> int:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                asset_id = self.add_asset(asset, imported_at)
                self.add_asset_source(asset_id, source_id, relative_path, fingerprint)
                self.set_thumbnail(asset_id, thumb)
                self.enqueue(job_kind, {"asset_id": asset_id})
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")
            return asset_id

    def _insert_asset(self, asset: NewAsset, imported_at: datetime) -> int:
        return self._write(
            """INSERT INTO asset (content_hash, kind, mime_type, byte_size, width, height,
                   taken_at, tz_offset_min, date_source, latitude, longitude, camera_make,
                   camera_model, orientation, library_path, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset.content_hash,
                asset.kind.value,
                asset.mime_type,
                asset.byte_size,
                asset.width,
                asset.height,
                _iso(asset.taken_at),
                asset.tz_offset_minutes,
                asset.date_source.value,
                asset.latitude,
                asset.longitude,
                asset.camera_make,
                asset.camera_model,
                asset.orientation,
                asset.library_path,
                _iso(imported_at),
            ),
        )

    def get_asset(self, asset_id: int) -> Asset | None:
        row = self._one("SELECT * FROM asset WHERE id = ?", (asset_id,))
        return self._asset(row) if row else None

    def list_assets(self, limit: int, cursor: str | None = None) -> Page:
        if cursor is None:
            rows = self._all(
                "SELECT * FROM asset ORDER BY taken_at DESC, id DESC LIMIT ?", (limit + 1,)
            )
        else:
            taken_at, asset_id = decode_cursor(cursor)
            rows = self._all(
                """SELECT * FROM asset WHERE (taken_at, id) < (?, ?)
                   ORDER BY taken_at DESC, id DESC LIMIT ?""",
                (taken_at, asset_id, limit + 1),
            )
        items = [self._asset(r) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last["taken_at"], last["id"])
        return Page(items, next_cursor)

    def count_assets(self) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM asset")
        return int(row["n"]) if row else 0

    def set_thumbnail(self, asset_id: int, thumb: RenderedImage) -> None:
        self._write(
            "UPDATE asset SET thumb_path = ?, thumb_w = ?, thumb_h = ? WHERE id = ?",
            (thumb.relative_path, thumb.width, thumb.height, asset_id),
        )

    def set_preview(self, asset_id: int, preview: RenderedImage) -> None:
        self._write(
            "UPDATE asset SET preview_path = ? WHERE id = ?", (preview.relative_path, asset_id)
        )

    def set_variant_of(self, asset_id: int, original_id: int) -> None:
        self._write("UPDATE asset SET variant_of = ? WHERE id = ?", (original_id, asset_id))

    # --- asset sources ---------------------------------------------------------------------

    def add_asset_source(
        self,
        asset_id: int,
        source_id: int,
        relative_path: str,
        fingerprint: Fingerprint | None = None,
    ) -> None:
        size = fingerprint.byte_size if fingerprint else None
        mtime = fingerprint.mtime_ns if fingerprint else None
        ctime = fingerprint.ctime_ns if fingerprint else None
        self._write(
            """INSERT INTO asset_source
                   (asset_id, source_id, relative_path, byte_size, mtime_ns, ctime_ns)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_id, relative_path) DO UPDATE SET
                   asset_id = excluded.asset_id, seen_at = excluded.seen_at,
                   byte_size = excluded.byte_size, mtime_ns = excluded.mtime_ns,
                   ctime_ns = excluded.ctime_ns""",
            (asset_id, source_id, relative_path, size, mtime, ctime),
        )
        self._write(
            "UPDATE asset SET first_source_id = ? WHERE id = ? AND first_source_id IS NULL",
            (source_id, asset_id),
        )

    def fingerprint_of(
        self, source_id: int, relative_path: str
    ) -> tuple[int, Fingerprint | None] | None:
        row = self._one(
            """SELECT asset_id, byte_size, mtime_ns, ctime_ns FROM asset_source
               WHERE source_id = ? AND relative_path = ?""",
            (source_id, relative_path),
        )
        if row is None:
            return None
        parts = (row["byte_size"], row["mtime_ns"], row["ctime_ns"])
        fingerprint = Fingerprint(*parts) if None not in parts else None
        return int(row["asset_id"]), fingerprint

    def previous_path_in_source(self, asset_id: int, source_id: int, exclude: str) -> str | None:
        row = self._one(
            """SELECT relative_path FROM asset_source
               WHERE asset_id = ? AND source_id = ? AND relative_path != ?
               ORDER BY seen_at LIMIT 1""",
            (asset_id, source_id, exclude),
        )
        return str(row["relative_path"]) if row else None

    def asset_id_for_source_path(self, source_id: int, relative_path: str) -> int | None:
        row = self._one(
            "SELECT asset_id FROM asset_source WHERE source_id = ? AND relative_path = ?",
            (source_id, relative_path),
        )
        return int(row["asset_id"]) if row else None

    def origins_of(self, asset_id: int) -> list[tuple[Source, str]]:
        rows = self._all(
            """SELECT s.*, a.relative_path FROM asset_source a JOIN source s ON s.id = a.source_id
               WHERE a.asset_id = ? ORDER BY s.id, a.relative_path""",
            (asset_id,),
        )
        return [(self._source(r), r["relative_path"]) for r in rows]

    # --- import runs -----------------------------------------------------------------------

    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                run_id = self._write(
                    """INSERT INTO import_run (source_id, status, started_at, finished_at,
                           ignored, summary_json, message) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.source_id,
                        report.status.value,
                        _iso(started_at),
                        _iso(finished_at),
                        report.ignored,
                        json.dumps(report.summary()),
                        report.message,
                    ),
                )
                self._conn.executemany(
                    """INSERT INTO import_item (run_id, relative_path, outcome, reason, asset_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    [
                        (run_id, i.relative_path, i.outcome.value, i.reason, i.asset_id)
                        for i in report.items
                    ],
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return run_id

    def get_import_report(self, run_id: int) -> ImportReport | None:
        run = self._one("SELECT * FROM import_run WHERE id = ?", (run_id,))
        if run is None:
            return None
        items = self._all("SELECT * FROM import_item WHERE run_id = ? ORDER BY rowid", (run_id,))
        return ImportReport(
            source_id=run["source_id"],
            status=RunStatus(run["status"]),
            items=[
                ItemResult(r["relative_path"], Outcome(r["outcome"]), r["reason"], r["asset_id"])
                for r in items
            ],
            ignored=run["ignored"],
            message=run["message"],
        )

    def list_import_runs(self, source_id: int | None = None) -> list[dict[str, object]]:
        sql = "SELECT * FROM import_run"
        params: tuple[object, ...] = ()
        if source_id is not None:
            sql += " WHERE source_id = ?"
            params = (source_id,)
        rows = self._all(sql + " ORDER BY id DESC", params)
        return [
            {
                "id": r["id"],
                "source_id": r["source_id"],
                "status": r["status"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "summary": json.loads(r["summary_json"]),
                "message": r["message"],
            }
            for r in rows
        ]

    # --- job queue -------------------------------------------------------------------------

    def enqueue(self, kind: str, payload: dict[str, object]) -> int:
        return self._write(
            "INSERT INTO job (kind, payload_json) VALUES (?, ?)", (kind, json.dumps(payload))
        )

    def enqueue_once(self, kind: str, payload: dict[str, object] | None = None) -> int | None:
        """Queue unless the same job (kind and payload) is already waiting."""
        body = json.dumps(payload or {}, sort_keys=True)
        with self._transaction():
            waiting = self._conn.execute(
                "SELECT 1 FROM job WHERE kind = ? AND payload_json = ? AND status = 'queued'",
                (kind, body),
            ).fetchone()
            if waiting:
                return None
            return self._write("INSERT INTO job (kind, payload_json) VALUES (?, ?)", (kind, body))

    def claim_next_job(
        self,
        now: datetime,
        *,
        only: Collection[str] | None = None,
        excluding: Collection[str] = (),
    ) -> Job | None:
        """Atomic across processes: one statement picks and marks the job (of a lane's kinds)."""
        where, params = "status = 'queued'", [_iso(now)]
        if only is not None:
            where += f" AND kind IN ({', '.join('?' for _ in only)})"
            params += list(only)
        if excluding:
            where += f" AND kind NOT IN ({', '.join('?' for _ in excluding)})"
            params += list(excluding)
        with self._lock:  # a write (UPDATE … RETURNING): on the writer
            row = self._conn.execute(
                f"""UPDATE job SET status = 'running', attempts = attempts + 1, updated_at = ?
                    WHERE id = (SELECT id FROM job WHERE {where} ORDER BY id LIMIT 1)
                    RETURNING id, kind, payload_json, attempts""",
                params,
            ).fetchone()
        if row is None:
            return None
        return Job(row["id"], row["kind"], json.loads(row["payload_json"]), row["attempts"])

    def prune_done_jobs(self, finished_before: datetime) -> int:
        """Forget finished jobs (C31): failures stay until someone looks at them."""
        return self._count(
            "DELETE FROM job WHERE status = 'done' AND updated_at < ?", (_iso(finished_before),)
        )

    def complete_job(self, job_id: int) -> None:
        self._write("UPDATE job SET status = 'done', error = NULL WHERE id = ?", (job_id,))

    def fail_job(self, job_id: int, error: str, retry: bool) -> None:
        status = "queued" if retry else "failed"
        self._write("UPDATE job SET status = ?, error = ? WHERE id = ?", (status, error, job_id))

    def list_jobs(self, status: str | None = None) -> list[dict[str, object]]:
        sql = "SELECT * FROM job"
        params: tuple[object, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        return [
            {
                "id": r["id"],
                "kind": r["kind"],
                "payload": json.loads(r["payload_json"]),
                "status": r["status"],
                "attempts": r["attempts"],
                "error": r["error"],
            }
            for r in self._all(sql + " ORDER BY id", params)
        ]

    def retry_job(self, job_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE job SET status = 'queued', error = NULL WHERE id = ? AND status = 'failed'",
                (job_id,),
            )
            return cur.rowcount > 0

    def release_job(self, job_id: int) -> None:
        self._write(
            """UPDATE job SET status = 'queued', attempts = MAX(attempts - 1, 0)
               WHERE id = ? AND status = 'running'""",
            (job_id,),
        )

    def recover_interrupted_jobs(self) -> int:
        """Jobs still 'running' at startup were cut off by a crash; queue them again."""
        with self._lock:
            cur = self._conn.execute("UPDATE job SET status = 'queued' WHERE status = 'running'")
            return cur.rowcount

    def job_counts(self) -> dict[str, int]:
        rows = self._all("SELECT status, COUNT(*) AS n FROM job GROUP BY status")
        counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
        counts.update({r["status"]: int(r["n"]) for r in rows})
        return counts
