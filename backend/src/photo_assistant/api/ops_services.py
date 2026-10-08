"""Composition for backups, library transfer and the doctor (guides: docs/guides/backups.md).

``api/services.py`` is the composition root and calls ``build_ops_services``. The CLI
(``api/cli_ops.py``) uses the same builders on its own.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from photo_assistant.adapters.backup_places import LocalBackupPlaces
from photo_assistant.adapters.filesystem import Blake3Hasher, SystemClock
from photo_assistant.adapters.key_vault import FileKeyVault
from photo_assistant.adapters.library_files import LocalFileTree, SqliteLibraryIndex
from photo_assistant.adapters.restic_backup import ResticBackup
from photo_assistant.adapters.sqlite_backup_store import SqliteBackupStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_snapshot import SqliteSnapshotter
from photo_assistant.adapters.system_probe import LocalSystemProbe
from photo_assistant.api.settings import OpsSettings
from photo_assistant.app.backup import BACKUP_DUE_JOB, BackupConfig, BackupService
from photo_assistant.app.doctor import DoctorConfig
from photo_assistant.app.library_transfer import LibraryTransfer
from photo_assistant.app.periodic import Periodic, PeriodicTask
from photo_assistant.domain.library_paths import nested_or_same
from photo_assistant.ports.backup import JobQueue, RepositoryMirror

DATABASE = "library.db"


def default_key_dir() -> Path:
    return Path.home() / ".config" / "photo-assistant" / "backup-keys"


@dataclass(frozen=True, slots=True)
class RcloneTool:
    """How this machine runs rclone (the same binary and config the cloud sources use)."""

    binary: str = "rclone"
    config: Path | None = None


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
    data_root: Path,
    ops: OpsSettings,
    *,
    db: Database,
    rclone: RcloneTool,
    queue: JobQueue | None = None,
    source_roots: Callable[[], Sequence[Path]] = lambda: (),
    mirror: RepositoryMirror | None = None,
) -> tuple[BackupService, SqliteBackupStore]:
    """``db``: the process's one Database. ``queue``: the server's job queue; the command
    line has none and runs a backup itself, in the foreground."""
    database = data_root / DATABASE
    key_dir = (ops.backup_key_dir or default_key_dir()).expanduser()
    if nested_or_same(key_dir.resolve(), data_root.expanduser().resolve()):
        raise ValueError(
            "PA_BACKUP_KEY_DIR must be outside the library: a backup can't hold its key"
        )
    store = SqliteBackupStore(db)
    service = BackupService(
        store=store,
        engine=ResticBackup(
            binary=ops.restic_binary,
            cache_dir=ops.restic_cache_dir,
            rclone_binary=rclone.binary,
            rclone_config=rclone.config,
        ),
        snapshotter=SqliteSnapshotter(database),
        hasher=Blake3Hasher(),
        clock=SystemClock(),
        config=BackupConfig(
            data_root=data_root,
            restore_sample=ops.backup_restore_sample,
            scratch_dir=ops.backup_scratch_dir,
            source_roots=source_roots,
        ),
        queue=queue,
        places=LocalBackupPlaces(rclone.binary, rclone.config),
        vault=FileKeyVault(key_dir),
        database_integrity=LocalSystemProbe().database_integrity,
        mirror=mirror,
    )
    return service, store


def build_ops_services(
    data_root: Path,
    ops: OpsSettings,
    *,
    db: Database,
    rclone: RcloneTool,
    queue: JobQueue,
    housekeeping: Sequence[PeriodicTask] = (),
    source_roots: Callable[[], Sequence[Path]] = lambda: (),
    mirror: RepositoryMirror | None = None,
) -> OpsServices:
    """For the server. ``housekeeping``: further periodic tasks of other areas (trash purge,
    face clustering). ``source_roots``: the library's source folders (backups may not overlap
    them). ``mirror``: where local backups can keep an off-site copy (Proton Drive), if
    anywhere."""
    backup, store = build_backup_service(
        data_root,
        ops,
        db=db,
        rclone=rclone,
        queue=queue,
        source_roots=source_roots,
        mirror=mirror,
    )
    # the check only enqueues: the backups themselves run on the worker's long-job lane
    check = PeriodicTask(
        "due backups", ops.backup_poll_seconds, lambda: queue.enqueue_once(BACKUP_DUE_JOB)
    )
    return OpsServices(
        backup, store, Periodic([*([check] if ops.backup_enabled else []), *housekeeping])
    )


def doctor_sample() -> Path:
    """A tiny synthetic iPhone HEIC (the IMG_1004 test fixture), shipped with the package."""
    return Path(str(resources.files("photo_assistant.adapters") / "samples" / "doctor-check.heic"))


def build_doctor_config(data_root: Path, min_free_gb: float) -> DoctorConfig:
    return DoctorConfig(data_root, doctor_sample(), int(min_free_gb * 1000**3))


def build_library_transfer() -> LibraryTransfer:
    hasher = Blake3Hasher()
    return LibraryTransfer(
        files=LocalFileTree(hasher),
        hasher=hasher,
        snapshot_database=lambda db, dest: SqliteSnapshotter(db).snapshot(dest),
        open_index=SqliteLibraryIndex,
    )
