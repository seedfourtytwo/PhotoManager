"""SQLite implementation of the BackupStore port (tables from migration 0016).

It shares the process's one ``Database`` (writer, lock and per-thread readers) with every other
store, and needs nothing from SqliteRepository.
"""

import json
import sqlite3
from datetime import UTC, datetime

from photo_assistant.adapters.sqlite_base import SqliteBase, iso_text
from photo_assistant.domain.backup import (
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    Retention,
    RunKind,
    RunOutcome,
    TargetSettings,
)
from photo_assistant.ports.backup import AssetFile, BackupTargetExistsError


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
        key_saved_at=_when(row["key_saved_at"]),
        mirror_path=row["mirror_path"],
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


class SqliteBackupStore(SqliteBase):
    """On the process's one ``Database`` (sqlite_database.py)."""

    # --- targets ---------------------------------------------------------------------------

    def add_target(self, target: NewBackupTarget, created_at: datetime) -> BackupTarget:
        try:
            target_id = self._write(
                """INSERT INTO backup_target (label, kind, repository, password_file, schedule,
                       quiet_window, retention_json, created_at, key_saved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    target.label,
                    target.kind.value,
                    target.repository,
                    target.password_file,
                    target.schedule,
                    target.quiet_window,
                    json.dumps(target.retention.as_dict()),
                    iso_text(created_at),
                    iso_text(created_at) if target.key_saved else None,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise BackupTargetExistsError(
                f"a backup target named {target.label!r} already exists"
            ) from exc
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

    def mark_key_saved(self, target_id: int, at: datetime) -> None:
        self._write(
            "UPDATE backup_target SET key_saved_at = ? WHERE id = ?", (iso_text(at), target_id)
        )

    def set_target_mirror(self, target_id: int, mirror_path: str | None) -> None:
        self._write(
            "UPDATE backup_target SET mirror_path = ? WHERE id = ?", (mirror_path, target_id)
        )

    def library_bytes(self) -> int:
        row = self._one("SELECT COALESCE(SUM(byte_size), 0) FROM asset")
        return int(row[0]) if row else 0

    def set_target_settings(self, target_id: int, settings: TargetSettings) -> None:
        self._write(
            """UPDATE backup_target SET schedule = ?, quiet_window = ?, retention_json = ?
               WHERE id = ?""",
            (
                settings.schedule,
                settings.quiet_window,
                json.dumps(settings.retention.as_dict()),
                target_id,
            ),
        )

    # --- runs ------------------------------------------------------------------------------

    def start_run(self, target_id: int, kind: RunKind, started_at: datetime) -> int:
        return self._write(
            "INSERT INTO backup_run (target_id, kind, status, started_at) VALUES (?, ?, ?, ?)",
            (target_id, kind.value, BackupRunStatus.RUNNING.value, iso_text(started_at)),
        )

    def finish_run(self, run_id: int, finished_at: datetime, outcome: RunOutcome) -> None:
        self._write(
            """UPDATE backup_run SET status = ?, finished_at = ?, snapshot_id = ?,
                   bytes_added = ?, files_new = ?, files_changed = ?, repo_bytes = ?,
                   error = ?, details = ?
               WHERE id = ?""",
            (
                outcome.status.value,
                iso_text(finished_at),
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
        return self._count(
            """UPDATE backup_run SET status = ?, finished_at = ?,
                   error = 'interrupted (the app stopped during the run)'
               WHERE status = ?""",
            (BackupRunStatus.FAILED.value, iso_text(now), BackupRunStatus.RUNNING.value),
        )

    # --- assets (read-only) ----------------------------------------------------------------

    def sample_assets(self, count: int, imported_before: datetime) -> list[AssetFile]:
        rows = self._all(
            """SELECT id, content_hash, library_path, thumb_path, preview_path FROM asset
               WHERE imported_at <= ? ORDER BY RANDOM() LIMIT ?""",
            (iso_text(imported_before.astimezone(UTC)), count),
        )
        return [
            AssetFile(
                r["id"], r["content_hash"], r["library_path"], r["thumb_path"], r["preview_path"]
            )
            for r in rows
        ]
