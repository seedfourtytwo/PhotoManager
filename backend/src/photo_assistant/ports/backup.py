"""Ports for backups (FEATURES 9b). The restic adapter implements BackupEngine."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.backup import (
    BackupRun,
    BackupTarget,
    NewBackupTarget,
    Retention,
    RunKind,
    RunOutcome,
)


class BackupError(RuntimeError):
    """A backup operation failed. The message says what happened and what to do."""


class WrongPasswordError(BackupError):
    pass


class RepositoryNotFoundError(BackupError):
    pass


class PasswordFileError(BackupError):
    pass


class RepositoryLockedError(BackupError):
    pass


class BackupToolMissingError(BackupError):
    pass


class IncompleteBackupError(BackupError):
    """A snapshot was written but some files could not be read."""


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    location: str  # local path or "rclone:<remote>:<path>"
    password_file: Path


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    snapshot_id: str
    files_new: int
    files_changed: int
    bytes_added: int
    bytes_processed: int


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    snapshot_id: str
    time: datetime  # timezone-aware


class BackupEngine(Protocol):
    def ensure_repository(self, repo: RepositoryRef) -> bool:
        """Create the repository if it does not exist yet. True if it was created."""
        ...

    def backup(self, repo: RepositoryRef, root: Path, folders: Sequence[str]) -> SnapshotSummary:
        """Snapshot the folders (relative to ``root``) that exist. Only ever reads ``root``."""
        ...

    def forget(self, repo: RepositoryRef, retention: Retention) -> None:
        """Apply the retention policy and prune unreferenced data."""
        ...

    def check(self, repo: RepositoryRef, read_data_subset: str | None = None) -> None: ...

    def latest_snapshot(self, repo: RepositoryRef) -> SnapshotInfo | None: ...

    def restore(
        self, repo: RepositoryRef, snapshot_id: str, paths: Sequence[str], target: Path
    ) -> None:
        """Restore the given data-root-relative paths under ``target`` (never the library)."""
        ...

    def repository_size(self, repo: RepositoryRef) -> int: ...


class DatabaseSnapshotter(Protocol):
    def snapshot(self, destination: Path) -> None:
        """Write a consistent copy of the live database (online backup API), atomically."""
        ...


@dataclass(frozen=True, slots=True)
class AssetFile:
    """The files one asset owns in the library, relative to the data root."""

    asset_id: int
    content_hash: str
    library_path: str
    thumb_path: str | None = None
    preview_path: str | None = None


class BackupStore(Protocol):
    def add_target(self, target: NewBackupTarget, created_at: datetime) -> BackupTarget:
        """Raises ValueError if the label is taken."""
        ...

    def get_target(self, target_id: int) -> BackupTarget | None: ...
    def list_targets(self) -> list[BackupTarget]: ...
    def set_target_enabled(self, target_id: int, enabled: bool) -> None: ...
    def start_run(self, target_id: int, kind: RunKind, started_at: datetime) -> int: ...
    def finish_run(self, run_id: int, finished_at: datetime, outcome: RunOutcome) -> None: ...
    def get_run(self, run_id: int) -> BackupRun | None: ...
    def list_runs(self, target_id: int, limit: int = 50) -> list[BackupRun]: ...
    def last_run(
        self, target_id: int, kind: RunKind, *, succeeded_only: bool = False
    ) -> BackupRun | None: ...
    def recover_interrupted_runs(self, now: datetime) -> int:
        """Mark runs cut off by a crash as failed; returns how many."""
        ...

    def sample_assets(self, count: int, imported_before: datetime) -> list[AssetFile]:
        """A random sample of assets imported before the given moment."""
        ...


class JobQueue(Protocol):
    def enqueue(self, kind: str, payload: dict[str, object]) -> int: ...
    def enqueue_once(self, kind: str) -> int | None:
        """Queue a payload-less job unless one of that kind is already waiting."""
        ...
