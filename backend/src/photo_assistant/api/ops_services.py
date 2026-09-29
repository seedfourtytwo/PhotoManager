"""Composition for backups, library transfer and the doctor (docs/wiring/ops.md).

``api/services.py`` stays the composition root; it calls ``build_ops_services`` once the
integrator wires it in. The CLI (``api/cli_ops.py``) uses the same builders on its own.
"""

from dataclasses import dataclass
from pathlib import Path

from photo_assistant.adapters.filesystem import Blake3Hasher, SystemClock
from photo_assistant.adapters.library_files import LocalFileTree, SqliteLibraryIndex
from photo_assistant.adapters.restic_backup import ResticBackup
from photo_assistant.adapters.sqlite_backup_store import SqliteBackupStore
from photo_assistant.adapters.sqlite_repository import open_database
from photo_assistant.adapters.sqlite_snapshot import SqliteSnapshotter
from photo_assistant.api.ops_settings import OpsSettings
from photo_assistant.app.backup import BackupConfig, BackupService
from photo_assistant.app.library_transfer import LibraryTransfer
from photo_assistant.app.periodic import Periodic, PeriodicTask
from photo_assistant.ports.backup import JobQueue

DATABASE = "library.db"


@dataclass
class OpsServices:
    backup: BackupService
    backup_store: SqliteBackupStore
    periodic: Periodic

    def start(self) -> None:
        """Server startup: settle runs a crash cut off, then start the periodic checks."""
        self.backup.recover_interrupted()
        self.periodic.start()

    def close(self) -> None:
        self.periodic.stop()
        self.backup_store.close()


def build_backup_service(
    data_root: Path, ops: OpsSettings, queue: JobQueue | None = None
) -> tuple[BackupService, SqliteBackupStore]:
    database = data_root / DATABASE
    # Own connection (WAL); migrations are a no-op when the main services opened it first.
    store = SqliteBackupStore(open_database(database, backup_dir=data_root / "db-backups"))
    service = BackupService(
        store=store,
        engine=ResticBackup(binary=ops.restic_binary, cache_dir=ops.restic_cache_dir),
        snapshotter=SqliteSnapshotter(database),
        hasher=Blake3Hasher(),
        clock=SystemClock(),
        config=BackupConfig(
            data_root=data_root,
            restore_sample=ops.backup_restore_sample,
            scratch_dir=ops.backup_scratch_dir,
        ),
        queue=queue,
    )
    return service, store


def build_ops_services(
    data_root: Path, ops: OpsSettings | None = None, queue: JobQueue | None = None
) -> OpsServices:
    ops = ops or OpsSettings()
    backup, store = build_backup_service(data_root, ops, queue)
    tasks = [PeriodicTask("due backups", ops.backup_poll_seconds, backup.run_due)]
    return OpsServices(backup, store, Periodic(tasks if ops.backup_enabled else []))


def build_library_transfer() -> LibraryTransfer:
    hasher = Blake3Hasher()
    return LibraryTransfer(
        files=LocalFileTree(hasher),
        hasher=hasher,
        snapshot_database=lambda db, dest: SqliteSnapshotter(db).snapshot(dest),
        open_index=SqliteLibraryIndex,
    )
