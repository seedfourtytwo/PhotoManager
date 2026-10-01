"""Backup targets, runs and retention (FEATURES 9b). Pure data and rules, no I/O."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from photo_assistant.domain.schedule import Schedule, parse_schedule, parse_window

# What a backup contains, relative to the data root (FEATURES 9b.4). ``derived/`` (thumbnails,
# previews) is rebuildable and skipped; ``db-snapshot/`` is a consistent copy of library.db
# taken with SQLite's online backup API just before each run: the live .db is never copied.
DB_SNAPSHOT_DIR = "db-snapshot"
DB_SNAPSHOT_FILE = "library.db"
BACKUP_FOLDERS = ("originals", "recipes", "config", "inbox", DB_SNAPSHOT_DIR)


class TargetKind(StrEnum):
    LOCAL = "local"  # a folder: external disk, mounted NAS share
    RCLONE = "rclone"  # restic's rclone backend: sftp to the server, SMB, any cloud


class RunKind(StrEnum):
    BACKUP = "backup"
    CHECK = "check"
    RESTORE_TEST = "restore_test"


class BackupRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def target_kind(repository: str) -> TargetKind:
    return TargetKind.RCLONE if repository.startswith("rclone:") else TargetKind.LOCAL


@dataclass(frozen=True, slots=True)
class Retention:
    """How many snapshots restic keeps after each backup (``forget --prune``)."""

    daily: int = 7
    weekly: int = 4
    monthly: int = 12

    def __post_init__(self) -> None:
        values = (self.daily, self.weekly, self.monthly)
        if any(v < 0 for v in values) or not any(values):
            raise ValueError("retention must keep at least one snapshot and no negative counts")

    def as_dict(self) -> dict[str, int]:
        return {"daily": self.daily, "weekly": self.weekly, "monthly": self.monthly}


@dataclass(frozen=True, slots=True)
class NewBackupTarget:
    label: str
    repository: str  # a local absolute path, or "rclone:<remote>:<path>"
    password_file: str  # absolute path on this machine, outside the library
    schedule: str = "daily 02:30"
    quiet_window: str | None = None
    retention: Retention = Retention()

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("a backup target needs a name")
        if not self.repository.strip():
            raise ValueError("a backup target needs a repository location")
        parse_schedule(self.schedule)  # raise InvalidScheduleError early
        parse_window(self.quiet_window)

    @property
    def kind(self) -> TargetKind:
        return target_kind(self.repository)


@dataclass(frozen=True, slots=True)
class BackupTarget:
    id: int
    label: str
    repository: str
    password_file: str
    schedule: str
    quiet_window: str | None
    retention: Retention
    enabled: bool
    created_at: datetime

    @property
    def kind(self) -> TargetKind:
        return target_kind(self.repository)

    @property
    def parsed_schedule(self) -> Schedule:
        return parse_schedule(self.schedule)


@dataclass(frozen=True, slots=True)
class BackupRun:
    id: int
    target_id: int
    kind: RunKind
    status: BackupRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    snapshot_id: str | None = None
    bytes_added: int | None = None
    files_new: int | None = None
    files_changed: int | None = None
    repo_bytes: int | None = None
    error: str | None = None
    details: str | None = None


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """What finishing a run records."""

    status: BackupRunStatus
    snapshot_id: str | None = None
    bytes_added: int | None = None
    files_new: int | None = None
    files_changed: int | None = None
    repo_bytes: int | None = None
    error: str | None = None
    details: str | None = None


@dataclass(frozen=True, slots=True)
class TargetStatus:
    """One line of the status page (FEATURES 9b.7)."""

    target: BackupTarget
    last_success_at: datetime | None
    last_run: BackupRun | None
    repo_bytes: int | None
    next_run_at: datetime | None
    overdue: bool

    @property
    def failing(self) -> bool:
        return self.last_run is not None and self.last_run.status is BackupRunStatus.FAILED

    @property
    def needs_attention(self) -> bool:
        """Drives the warning banner: overdue or the last attempt failed."""
        return self.target.enabled and (self.overdue or self.failing)


@dataclass(frozen=True, slots=True)
class RestoreCheck:
    library_path: str
    ok: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreTestReport:
    snapshot_id: str | None
    checks: tuple[RestoreCheck, ...]

    @property
    def ok(self) -> bool:
        return self.snapshot_id is not None and all(c.ok for c in self.checks)

    def summary(self) -> str:
        if self.snapshot_id is None:
            return "no snapshot to restore from yet"
        bad = [c for c in self.checks if not c.ok]
        text = f"restored {len(self.checks)} photos from {self.snapshot_id[:8]}"
        if not bad:
            return f"{text}; every hash matches"
        listed = "; ".join(f"{c.library_path}: {c.reason}" for c in bad[:5])
        return f"{text}; {len(bad)} failed: {listed}"
