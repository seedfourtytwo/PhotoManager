"""SQLite implementation of the Repository port (the migration runner and the shared
connections live in ``sqlite_database``; ``open_database`` is re-exported here)."""

import json
import sqlite3
import uuid
from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from pathlib import Path

from photo_assistant.adapters.sqlite_access import AccessMixin, UnknownUserError
from photo_assistant.adapters.sqlite_accounts import AccountsMixin, utc_text
from photo_assistant.adapters.sqlite_albums import AlbumsMixin
from photo_assistant.adapters.sqlite_base import (
    SqliteBase,
    asset_from_row,
    decode_cursor,
    encode_cursor,
    source_from_row,
)
from photo_assistant.adapters.sqlite_base import iso_text as _iso
from photo_assistant.adapters.sqlite_database import Database, open_database
from photo_assistant.adapters.sqlite_database import migrations as _migrations
from photo_assistant.adapters.sqlite_edits import EditsMixin
from photo_assistant.adapters.sqlite_enrich import EnrichMixin
from photo_assistant.adapters.sqlite_home import HomeMixin
from photo_assistant.adapters.sqlite_library import LibraryMixin
from photo_assistant.adapters.sqlite_review import ReviewMixin
from photo_assistant.adapters.sqlite_trash import TrashMixin
from photo_assistant.domain.access import SourceAccess, default_source_access
from photo_assistant.domain.model import (
    REPORT_ORDER,
    Asset,
    ImportReport,
    ItemResult,
    NewAsset,
    Outcome,
    RunStatus,
    Source,
)
from photo_assistant.domain.recheck import Recheck
from photo_assistant.ports import (
    IMPORT_RUNS_LISTED,
    DuplicateAssetError,
    Fingerprint,
    Job,
    Page,
    RenderedImage,
    SourceExistsError,
)

__all__ = ["Database", "DuplicateAssetError", "SqliteRepository", "_migrations", "open_database"]

# REPORT_ORDER as the WHEN arms of a SQL CASE over import_item.outcome (fixed enum values)
_REPORT_ORDER = " ".join(f"WHEN '{o.value}' THEN {n}" for n, o in enumerate(REPORT_ORDER))


def _run_row(r: sqlite3.Row) -> dict[str, object]:
    return {
        "id": r["id"],
        "source_id": r["source_id"],
        "status": r["status"],
        "started_at": r["started_at"],
        "finished_at": r["finished_at"],
        "summary": json.loads(r["summary_json"]),
        "message": r["message"],
    }


def _job_row(r: sqlite3.Row) -> dict[str, object]:
    return {
        "id": r["id"],
        "kind": r["kind"],
        "payload": json.loads(r["payload_json"]),
        "status": r["status"],
        "attempts": r["attempts"],
        "error": r["error"],
        "run_after": r["run_after"],
    }


class SqliteRepository(
    AccountsMixin,
    AccessMixin,
    LibraryMixin,
    HomeMixin,
    AlbumsMixin,
    EditsMixin,
    EnrichMixin,
    TrashMixin,
    ReviewMixin,
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

    _source = staticmethod(source_from_row)

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
                for user_id in {owner_id, *(uid for uid, _ in grants.users)} - {None}:
                    known = self._conn.execute("SELECT 1 FROM user WHERE id = ?", (user_id,))
                    if not known.fetchone():
                        raise UnknownUserError(f"no user with id {user_id}")
                placeholder = root if isinstance(root, str) else f"pending:{uuid.uuid4().hex}"
                source_id = self._write(
                    """INSERT INTO source (kind, label, root, owner_id, config_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (kind, label, placeholder, owner_id, json.dumps(config) if config else None),
                )
                if not isinstance(root, str):
                    placeholder = root(source_id)
                    self._write("UPDATE source SET root = ? WHERE id = ?", (placeholder, source_id))
                self._grant(source_id, grants)
        except sqlite3.IntegrityError as exc:
            if "source.root" not in str(exc):
                raise  # not a folder clash: don't report it as one
            raise SourceExistsError(f"folder is already a source: {placeholder}") from exc
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

    def set_source_recheck(self, source_id: int, recheck: Recheck) -> None:
        self._write("UPDATE source SET recheck = ? WHERE id = ?", (recheck.value, source_id))

    def last_check_attempts(self, job_kind: str) -> dict[int, datetime]:
        """Source id → when its latest check started, whether it worked or not: the later of
        its newest import run and its newest check job that a worker picked up and that did
        not finish. That job covers a check that died before any report: its ``updated_at``
        is when it was claimed or, once it failed, when it failed. A finished job has its
        run, whose start counts (the job's own time is by then the end of the check)."""
        runs = self._all(
            """SELECT source_id, started_at FROM import_run
               WHERE id IN (SELECT MAX(id) FROM import_run GROUP BY source_id)"""
        )
        attempts = {int(r["source_id"]): datetime.fromisoformat(r["started_at"]) for r in runs}
        for source_id, claimed_at in self._check_jobs(
            job_kind, "attempts > 0 AND status <> 'done'"
        ):
            last = attempts.get(source_id)
            attempts[source_id] = claimed_at if last is None else max(last, claimed_at)
        return attempts

    def sources_being_checked(self, job_kind: str) -> set[int]:
        """Sources with a check waiting or running."""
        jobs = self._check_jobs(job_kind, "status IN ('queued', 'running')")
        return {source_id for source_id, _ in jobs}

    def _check_jobs(self, job_kind: str, where: str) -> list[tuple[int, datetime]]:
        """(source id, last touched) of the jobs of this kind that match ``where``."""
        rows = self._all(
            f"""SELECT json_extract(payload_json, '$.source_id') AS source_id, updated_at
                FROM job WHERE kind = ? AND {where}""",
            (job_kind,),
        )
        return [
            (int(r["source_id"]), datetime.fromisoformat(r["updated_at"]))
            for r in rows
            if r["source_id"] is not None
        ]

    def rename_source(self, source_id: int, label: str) -> None:
        self._write("UPDATE source SET label = ? WHERE id = ?", (label, source_id))

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
        with self._transaction():
            asset_id = self.add_asset(asset, imported_at)
            self.add_asset_source(asset_id, source_id, relative_path, fingerprint)
            self.set_thumbnail(asset_id, thumb)
            self.enqueue(job_kind, {"asset_id": asset_id})
            return asset_id

    def _insert_asset(self, asset: NewAsset, imported_at: datetime) -> int:
        return self._write(
            """INSERT INTO asset (content_hash, kind, mime_type, byte_size, width, height,
                   taken_at, tz_offset_min, date_source, latitude, longitude, camera_make,
                   camera_model, orientation, library_path, imported_at,
                   f_number, exposure_time, iso, focal_length)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                asset.exposure.f_number,
                asset.exposure.exposure_time,
                asset.exposure.iso,
                asset.exposure.focal_length,
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

    # --- import runs -----------------------------------------------------------------------

    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int:
        with self._transaction():
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
        return run_id

    def set_import_run_message(self, run_id: int, message: str) -> None:
        self._write("UPDATE import_run SET message = ? WHERE id = ?", (message, run_id))

    def get_import_run(self, run_id: int) -> dict[str, object] | None:
        """One run as ``list_import_runs`` gives it, without its files."""
        row = self._one("SELECT * FROM import_run WHERE id = ?", (run_id,))
        return _run_row(row) if row else None

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

    def import_items_page(
        self, run_id: int, outcome: Outcome | None, limit: int, offset: int
    ) -> tuple[list[ItemResult], int]:
        """One page of a run's files and how many there are in all (of ``outcome``, if given).
        What needs a look comes first (failed, skipped, duplicates), then the files seen
        before and the imported ones; within an outcome, in the order they were handled."""
        where, params = "run_id = ?", list[object]([run_id])
        if outcome is not None:
            where += " AND outcome = ?"
            params.append(outcome.value)
        total = self._scalar(f"SELECT COUNT(*) FROM import_item WHERE {where}", params)
        rows = self._all(
            f"""SELECT * FROM import_item WHERE {where}
                ORDER BY CASE outcome {_REPORT_ORDER} END, rowid LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        )
        items = [
            ItemResult(r["relative_path"], Outcome(r["outcome"]), r["reason"], r["asset_id"])
            for r in rows
        ]
        return items, total

    def import_run_summary(self, run_id: int) -> dict[str, int] | None:
        """The counts saved with the run: they outlive its per-file rows (prune_import_items)."""
        row = self._one("SELECT summary_json FROM import_run WHERE id = ?", (run_id,))
        return json.loads(row["summary_json"]) if row else None

    def prune_import_items(self, keep_runs: int) -> int:
        """Delete the per-file rows of all but each source's ``keep_runs`` newest runs (one row
        per file seen on every rescan adds up). The runs and their summaries stay."""
        return self._count(
            """DELETE FROM import_item WHERE run_id IN (
                   SELECT id FROM (
                       SELECT id, ROW_NUMBER() OVER (PARTITION BY source_id ORDER BY id DESC) AS n
                       FROM import_run)
                   WHERE n > ?)""",
            (keep_runs,),
        )

    def list_import_runs(
        self, source_id: int | None = None, limit: int = IMPORT_RUNS_LISTED
    ) -> list[dict[str, object]]:
        """Newest first, at most ``limit``."""
        sql = "SELECT * FROM import_run"
        params: tuple[object, ...] = ()
        if source_id is not None:
            sql += " WHERE source_id = ?"
            params = (source_id,)
        rows = self._all(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))
        return [_run_row(r) for r in rows]

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
        owner: str | None = None,
        only: Collection[str] | None = None,
        excluding: Collection[str] = (),
    ) -> Job | None:
        """Atomic across processes: one statement picks and marks the job (of a lane's kinds).

        The oldest queued job whose time has come. ``waiting`` lists the kinds that have queued
        jobs with one index seek each, so a lane never walks the jobs of the others."""
        lane, kinds = "", list[str]()
        if only is not None:
            lane += f" AND kind IN ({', '.join('?' for _ in only)})"
            kinds += list(only)
        if excluding:
            lane += f" AND kind NOT IN ({', '.join('?' for _ in excluding)})"
            kinds += list(excluding)
        at = utc_text(now)
        with self._lock:  # a write (UPDATE … RETURNING): on the writer
            row = self._conn.execute(
                f"""WITH RECURSIVE waiting(kind) AS (
                        SELECT MIN(kind) FROM job WHERE status = 'queued'
                        UNION ALL
                        SELECT (SELECT MIN(kind) FROM job
                                WHERE status = 'queued' AND kind > waiting.kind)
                        FROM waiting WHERE waiting.kind IS NOT NULL)
                    UPDATE job SET status = 'running', attempts = attempts + 1, updated_at = ?,
                        run_after = NULL, claimed_by = ?, claimed_at = ?
                    WHERE id = (
                        SELECT MIN((SELECT id FROM job
                                    WHERE status = 'queued' AND kind = waiting.kind
                                      AND (run_after IS NULL OR run_after <= ?)
                                    ORDER BY id LIMIT 1))
                        FROM waiting WHERE kind IS NOT NULL{lane})
                    RETURNING id, kind, payload_json, attempts""",
                [_iso(now), owner, at, at, *kinds],
            ).fetchone()
        if row is None:
            return None
        return Job(row["id"], row["kind"], json.loads(row["payload_json"]), row["attempts"])

    def prune_done_jobs(self, finished_before: datetime) -> int:
        """Forget finished jobs (C31): failures stay until someone looks at them."""
        return self._count(
            "DELETE FROM job WHERE status = 'done' AND updated_at < ?", (_iso(finished_before),)
        )

    def complete_job(self, job_id: int, now: datetime | None = None) -> None:
        """``now``: when the run ended; finished jobs are pruned by that time."""
        self._write(
            """UPDATE job SET status = 'done', error = NULL, updated_at = COALESCE(?, updated_at)
               WHERE id = ?""",
            (_iso(now) if now else None, job_id),
        )

    def fail_job(
        self,
        job_id: int,
        error: str,
        retry: bool,
        run_after: datetime | None = None,
        *,
        now: datetime | None = None,
    ) -> None:
        """``retry``: queue it again, not to be claimed before ``run_after`` (None = at once).
        ``now``: when the attempt ended."""
        status = "queued" if retry else "failed"
        wait = utc_text(run_after) if retry and run_after is not None else None
        self._write(
            """UPDATE job SET status = ?, error = ?, run_after = ?,
                   updated_at = COALESCE(?, updated_at)
               WHERE id = ?""",
            (status, error, wait, _iso(now) if now else None, job_id),
        )

    def list_jobs(self, status: str | None = None) -> list[dict[str, object]]:
        """``run_after`` is set on a queued job that waits for its next attempt; the status
        ``waiting`` lists just those (what ``job_counts`` counts as waiting)."""
        sql = "SELECT * FROM job"
        params: tuple[object, ...] = ()
        if status == "waiting":
            sql += " WHERE status = 'queued' AND run_after IS NOT NULL"
        elif status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        return [_job_row(r) for r in self._all(sql + " ORDER BY id", params)]

    def get_job(self, job_id: int) -> dict[str, object] | None:
        """One job as ``list_jobs`` gives it."""
        row = self._one("SELECT * FROM job WHERE id = ?", (job_id,))
        return _job_row(row) if row else None

    def retry_job(self, job_id: int) -> bool:
        """By hand, from the admin screen: a fresh set of attempts, starting now."""
        with self._lock:
            cur = self._conn.execute(
                """UPDATE job SET status = 'queued', error = NULL, attempts = 0,
                       run_after = NULL, claimed_by = NULL, claimed_at = NULL
                   WHERE id = ? AND status = 'failed'""",
                (job_id,),
            )
            return cur.rowcount > 0

    def release_job(self, job_id: int) -> None:
        self._write(
            """UPDATE job SET status = 'queued', attempts = MAX(attempts - 1, 0),
                   claimed_by = NULL, claimed_at = NULL
               WHERE id = ? AND status = 'running'""",
            (job_id,),
        )

    def renew_claim(self, job_id: int, owner: str, now: datetime) -> None:
        """The heartbeat of a running job. Only its owner's: a job that was given up on and
        taken over by another process is not kept fresh by the first one."""
        self._write(
            "UPDATE job SET claimed_at = ? WHERE id = ? AND status = 'running' AND claimed_by = ?",
            (utc_text(now), job_id, owner),
        )

    def requeue_stale_jobs(self, stale_before: datetime) -> int:
        """Queue running jobs again whose claim was last renewed before ``stale_before`` (or
        never: rows from before leases existed): their process died. The interrupted run
        keeps counting as an attempt. A job with a fresh claim is another live process's."""
        return self._count(
            """UPDATE job SET status = 'queued', claimed_by = NULL, claimed_at = NULL
               WHERE status = 'running' AND (claimed_at IS NULL OR claimed_at < ?)""",
            (utc_text(stale_before),),
        )

    def job_counts(self) -> dict[str, int]:
        """By status; ``waiting`` are the queued jobs that wait for a retry time, counted
        apart so "queued" stays "work that is due"."""
        rows = self._all(  # one statement: both counts from the same moment
            """SELECT status, COUNT(*) AS n FROM job GROUP BY status
               UNION ALL
               SELECT 'waiting', COUNT(*) FROM job
               WHERE status = 'queued' AND run_after IS NOT NULL"""
        )
        counts = {"queued": 0, "waiting": 0, "running": 0, "done": 0, "failed": 0}
        counts.update({r["status"]: int(r["n"]) for r in rows})
        counts["queued"] -= counts["waiting"]
        return counts
