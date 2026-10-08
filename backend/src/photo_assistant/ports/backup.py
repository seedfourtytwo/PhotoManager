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
    PlaceFacts,
    Retention,
    RunKind,
    RunOutcome,
    TargetSettings,
)
from photo_assistant.domain.errors import ConflictError, UnavailableError


class BackupTargetExistsError(ConflictError, ValueError):
    """The name is taken by another backup target. (Still a ValueError, as it was before it
    joined the hierarchy.)"""


class BackupError(RuntimeError):
    """A backup operation failed. The message says what happened and what to do.

    Not a DomainError: BackupService records it on the backup run, and what failed may pass
    (a locked repository, an unplugged disk). The subclasses that can never pass by waiting
    and that a route answers are DomainErrors as well."""


class WrongPasswordError(BackupError):
    pass


class RepositoryNotFoundError(BackupError):
    pass


class PasswordFileError(BackupError, ConflictError):
    """The key file is gone, unreadable, or not one the app may show (409 on the recovery
    sheet)."""


class RepositoryLockedError(BackupError):
    pass


class BackupToolMissingError(BackupError, UnavailableError):
    """restic is not installed: waiting does not install it."""


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


@dataclass(frozen=True, slots=True)
class Disk:
    """An external disk that is plugged in and mounted."""

    path: str
    label: str
    free_bytes: int


class BackupPlaces(Protocol):
    """Where a backup could go on this machine, and what a given place is like."""

    def disks(self) -> list[Disk]: ...

    def remotes(self) -> list[str]:
        """Names of the cloud and network remotes set up in rclone; none if rclone is absent."""
        ...

    def facts(self, repository: str, data_root: Path) -> PlaceFacts:
        """Never raises: what can't be found out is reported as unknown or as a write error."""
        ...


class KeyVault(Protocol):
    """Keeps the keys the app makes for its backups, outside the library."""

    def create(self) -> tuple[Path, str]:
        """A new random key in a new file only this user can read: (file, key)."""
        ...

    def read(self, key_file: Path) -> str:
        """Raises PasswordFileError if the file is gone or unreadable."""
        ...

    def holds(self, key_file: Path) -> bool:
        """Is this path a file of the vault itself (symlinks and ``..`` resolved)?"""
        ...

    def discard(self, key_file: Path) -> None: ...


class MirrorError(BackupError):
    """The off-site copy could not be brought up to date; the message says why."""


class MirrorSignInError(MirrorError):
    """The cloud account is not signed in on this machine."""


@dataclass(frozen=True, slots=True)
class MirrorReport:
    uploaded: int  # files that were not in the copy before
    removed: int  # files the backup no longer has, taken out of the copy
    bytes_sent: int
    left_in_trash: int = 0  # of those, how many could only be trashed, not deleted for good


class RepositoryMirror(Protocol):
    """A second, off-site copy of a local backup repository (already encrypted)."""

    def mirror(self, repository: Path, remote_folder: str, state_file: Path) -> MirrorReport:
        """Make ``<remote_folder>/<repository's name>`` hold exactly the repository's files.
        ``state_file`` is the mirror's own bookkeeping; the repository is only read."""
        ...


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
        """Raises BackupTargetExistsError if the label is taken."""
        ...

    def get_target(self, target_id: int) -> BackupTarget | None: ...
    def list_targets(self) -> list[BackupTarget]: ...
    def set_target_enabled(self, target_id: int, enabled: bool) -> None: ...
    def mark_key_saved(self, target_id: int, at: datetime) -> None: ...
    def set_target_mirror(self, target_id: int, mirror_path: str | None) -> None: ...
    def library_bytes(self) -> int:
        """Bytes of every original the library holds: what a first backup has to store."""
        ...

    def set_target_settings(self, target_id: int, settings: TargetSettings) -> None: ...
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
    def enqueue_once(self, kind: str, payload: dict[str, object] | None = None) -> int | None:
        """Queue a payload-less job unless one of that kind is already waiting."""
        ...
