"""SQLite implementation of the Repository port, plus the tiny migration runner.

Migrations are numbered ``.sql`` files in ``migrations/``; ``PRAGMA user_version`` records the
last one applied. Before migrating an existing database, a consistent snapshot is written with
SQLite's online backup API (FEATURES 11.6).
"""

import base64
import json
import sqlite3
import threading
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.media_types import MediaKind
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

__all__ = ["DuplicateAssetError", "SqliteRepository", "open_database"]


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("photo_assistant.adapters") / "migrations"
    found = []
    for entry in folder.iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.read_text()))
    return sorted(found)


def _snapshot(conn: sqlite3.Connection, backup_dir: Path, version: int) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    target = sqlite3.connect(backup_dir / f"library-v{version}-{stamp}.db")
    with target:
        conn.backup(target)
    target.close()


def open_database(path: str | Path, backup_dir: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) and migrate. ``":memory:"`` is fine for tests."""
    is_file = str(path) != ":memory:"
    existed = is_file and Path(path).exists()
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if is_file:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    pending = [(n, sql) for n, sql in _migrations() if n > current]
    if pending and existed and backup_dir is not None:
        _snapshot(conn, backup_dir, current)
    for number, sql in pending:
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
    return conn


def _iso(value: datetime) -> str:
    return value.isoformat()


def _encode_cursor(taken_at: str, asset_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([taken_at, asset_id]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        taken_at, asset_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return str(taken_at), int(asset_id)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid cursor: {cursor!r}") from exc


class SqliteRepository:
    """Thread-safe enough for one API process plus a worker thread (one lock, WAL mode)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- helpers ---------------------------------------------------------------------------

    def _one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            row: sqlite3.Row | None = self._conn.execute(sql, params).fetchone()
            return row

    def _all(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _write(self, sql: str, params: tuple[object, ...] = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return int(cur.lastrowid or 0)

    # --- sources ---------------------------------------------------------------------------

    @staticmethod
    def _source(row: sqlite3.Row) -> Source:
        return Source(row["id"], row["label"], row["root"], bool(row["enabled"]), row["kind"])

    def add_source(self, label: str, root: str) -> Source:
        try:
            source_id = self._write("INSERT INTO source (label, root) VALUES (?, ?)", (label, root))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"folder is already a source: {root}") from exc
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

    @staticmethod
    def _asset(row: sqlite3.Row) -> Asset:
        return Asset(
            content_hash=row["content_hash"],
            kind=MediaKind(row["kind"]),
            mime_type=row["mime_type"],
            byte_size=row["byte_size"],
            width=row["width"],
            height=row["height"],
            taken_at=datetime.fromisoformat(row["taken_at"]),
            tz_offset_minutes=row["tz_offset_min"],
            date_source=DateSource(row["date_source"]),
            latitude=row["latitude"],
            longitude=row["longitude"],
            camera_make=row["camera_make"],
            camera_model=row["camera_model"],
            orientation=row["orientation"],
            library_path=row["library_path"],
            id=row["id"],
            imported_at=datetime.fromisoformat(row["imported_at"]),
            thumb_path=row["thumb_path"],
            preview_path=row["preview_path"],
            variant_of=row["variant_of"],
        )

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
            taken_at, asset_id = _decode_cursor(cursor)
            rows = self._all(
                """SELECT * FROM asset WHERE (taken_at, id) < (?, ?)
                   ORDER BY taken_at DESC, id DESC LIMIT ?""",
                (taken_at, asset_id, limit + 1),
            )
        items = [self._asset(r) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = _encode_cursor(last["taken_at"], last["id"])
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

    def claim_next_job(self, now: datetime) -> Job | None:
        """Atomic across processes: one statement picks and marks the job."""
        row = self._one(
            """UPDATE job SET status = 'running', attempts = attempts + 1, updated_at = ?
               WHERE id = (SELECT id FROM job WHERE status = 'queued' ORDER BY id LIMIT 1)
               RETURNING id, kind, payload_json, attempts""",
            (_iso(now),),
        )
        if row is None:
            return None
        return Job(row["id"], row["kind"], json.loads(row["payload_json"]), row["attempts"])

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
