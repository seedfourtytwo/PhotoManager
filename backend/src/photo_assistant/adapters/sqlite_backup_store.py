"""SQLite implementation of the BackupStore port (tables from migration 0040).

It takes its own connection to library.db (``open_database`` in the composition root), so it
needs nothing from SqliteRepository; WAL mode lets both write safely.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime

from photo_assistant.domain.backup import (
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    Retention,
    RunKind,
    RunOutcome,
)
from photo_assistant.ports.backup import AssetFile


def _iso(value: datetime) -> str:
    return value.isoformat()


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _target(row: sqlite3.Row) -> BackupTarget:
    return BackupTarget(
        id=row["id"],
        label=row["label"],
        repository=row["repository"],
        password_file=row["password_file"],
        schedule=row["schedule"],
        quiet_window=row["quiet_window"],
        retention=Retention(**json.loads(row["retention_json"])),
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _run(row: sqlite3.Row) -> BackupRun:
    return BackupRun(
        id=row["id"],
        target_id=row["target_id"],
        kind=RunKind(row["kind"]),
        status=BackupRunStatus(row["status"]),
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=_when(row["finished_at"]),
        snapshot_id=row["snapshot_id"],
        bytes_added=row["bytes_added"],
        files_new=row["files_new"],
        files_changed=row["files_changed"],
        repo_bytes=row["repo_bytes"],
        error=row["error"],
        details=row["details"],
    )


class SqliteBackupStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        self._conn = conn
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            row: sqlite3.Row | None = self._conn.execute(sql, params).fetchone()
            return row

    def _all(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _write(self, sql: str, params: tuple[object, ...] = ()) -> int:
        with self._lock:
            return int(self._conn.execute(sql, params).lastrowid or 0)

    # --- targets ---------------------------------------------------------------------------

    def add_target(self, target: NewBackupTarget, created_at: datetime) -> BackupTarget:
        try:
            target_id = self._write(
                """INSERT INTO backup_target (label, kind, repository, password_file, schedule,
                       quiet_window, retention_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    target.label,
                    target.kind.value,
                    target.repository,
                    target.password_file,
                    target.schedule,
                    target.quiet_window,
                    json.dumps(target.retention.as_dict()),
                    _iso(created_at),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"a backup target named {target.label!r} already exists") from exc
        found = self.get_target(target_id)
        assert found is not None
        return found

    def get_target(self, target_id: int) -> BackupTarget | None:
        row = self._one("SELECT * FROM backup_target WHERE id = ?", (target_id,))
        return _target(row) if row else None

    def list_targets(self) -> list[BackupTarget]:
        return [_target(r) for r in self._all("SELECT * FROM backup_target ORDER BY id")]

    def set_target_enabled(self, target_id: int, enabled: bool) -> None:
        self._write("UPDATE backup_target SET enabled = ? WHERE id = ?", (int(enabled), target_id))

    # --- runs ------------------------------------------------------------------------------

    def start_run(self, target_id: int, kind: RunKind, started_at: datetime) -> int:
        return self._write(
            "INSERT INTO backup_run (target_id, kind, status, started_at) VALUES (?, ?, ?, ?)",
            (target_id, kind.value, BackupRunStatus.RUNNING.value, _iso(started_at)),
        )

    def finish_run(self, run_id: int, finished_at: datetime, outcome: RunOutcome) -> None:
        self._write(
            """UPDATE backup_run SET status = ?, finished_at = ?, snapshot_id = ?,
                   bytes_added = ?, files_new = ?, files_changed = ?, repo_bytes = ?,
                   error = ?, details = ?
               WHERE id = ?""",
            (
                outcome.status.value,
                _iso(finished_at),
                outcome.snapshot_id,
                outcome.bytes_added,
                outcome.files_new,
                outcome.files_changed,
                outcome.repo_bytes,
                outcome.error,
                outcome.details,
                run_id,
            ),
        )

    def get_run(self, run_id: int) -> BackupRun | None:
        row = self._one("SELECT * FROM backup_run WHERE id = ?", (run_id,))
        return _run(row) if row else None

    def list_runs(self, target_id: int, limit: int = 50) -> list[BackupRun]:
        rows = self._all(
            "SELECT * FROM backup_run WHERE target_id = ? ORDER BY id DESC LIMIT ?",
            (target_id, limit),
        )
        return [_run(r) for r in rows]

    def last_run(
        self, target_id: int, kind: RunKind, *, succeeded_only: bool = False
    ) -> BackupRun | None:
        sql = "SELECT * FROM backup_run WHERE target_id = ? AND kind = ?"
        params: tuple[object, ...] = (target_id, kind.value)
        if succeeded_only:
            sql += " AND status = ?"
            params += (BackupRunStatus.SUCCEEDED.value,)
        row = self._one(sql + " ORDER BY id DESC LIMIT 1", params)
        return _run(row) if row else None

    def recover_interrupted_runs(self, now: datetime) -> int:
        """Runs still 'running' at startup were cut off (crash, power loss): mark them failed."""
        with self._lock:
            cur = self._conn.execute(
                """UPDATE backup_run SET status = ?, finished_at = ?,
                       error = 'interrupted (the app stopped during the run)'
                   WHERE status = ?""",
                (BackupRunStatus.FAILED.value, _iso(now), BackupRunStatus.RUNNING.value),
            )
            return cur.rowcount

    # --- assets (read-only) ----------------------------------------------------------------

    def sample_assets(self, count: int, imported_before: datetime) -> list[AssetFile]:
        rows = self._all(
            """SELECT id, content_hash, library_path, thumb_path, preview_path FROM asset
               WHERE imported_at <= ? ORDER BY RANDOM() LIMIT ?""",
            (_iso(imported_before.astimezone(UTC)), count),
        )
        return [
            AssetFile(
                r["id"], r["content_hash"], r["library_path"], r["thumb_path"], r["preview_path"]
            )
            for r in rows
        ]
