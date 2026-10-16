"""Backup targets, runs and retention (FEATURES 9b). Pure data and rules, no I/O."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from photo_assistant.domain.backup_errors import ErrorKind, error_kind
from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.library_paths import DATABASE_FILE, LIBRARY_FOLDERS
from photo_assistant.domain.schedule import (
    Every,
    QuietWindow,
    Schedule,
    is_due,
    parse_schedule,
    parse_window,
)

# What a backup contains, relative to the data root (FEATURES 9b.4). ``derived/`` (thumbnails,
# previews) is rebuildable and skipped; ``db-snapshot/`` is a consistent copy of library.db
# taken with SQLite's online backup API just before each run: the live .db is never copied.
DB_SNAPSHOT_DIR = "db-snapshot"
DB_SNAPSHOT_FILE = DATABASE_FILE
BACKUP_FOLDERS = (*LIBRARY_FOLDERS, DB_SNAPSHOT_DIR)

GB = 1000**3
MB = 1000**2
HEADROOM = 1.2  # a new backup place should hold the library and 20 % more
PROOF_EVERY = timedelta(days=7)  # how often a restore test proves each backup
PROOF_RETRY = timedelta(days=1)  # after a failed restore test
SKIP_RETRY = timedelta(minutes=15)  # how soon to look again for a place that was not connected


class InvalidBackupTargetError(InvalidError, ValueError):
    """A backup target, place or setting that will not do; the message says what to change.
    (Still a ValueError, as it was before it joined the hierarchy.)"""


class TargetKind(StrEnum):
    LOCAL = "local"  # a folder: external disk, mounted NAS share
    RCLONE = "rclone"  # restic's rclone backend: sftp to the server, SMB, any cloud


class RunKind(StrEnum):
    BACKUP = "backup"
    CHECK = "check"
    RESTORE_TEST = "restore_test"
    MIRROR = "mirror"  # bring the off-site copy (Proton Drive) up to date


class BackupRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"  # the place was not connected; nothing was attempted


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
            raise InvalidBackupTargetError(
                "retention must keep at least one snapshot and no negative counts"
            )

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
    # False for a key the app made: the owner must still confirm they kept a copy of it
    key_saved: bool = True

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise InvalidBackupTargetError("a backup target needs a name")
        if not self.repository.strip():
            raise InvalidBackupTargetError("a backup target needs a repository location")
        parse_schedule(self.schedule)  # raise InvalidScheduleError early
        parse_window(self.quiet_window)

    @property
    def kind(self) -> TargetKind:
        return target_kind(self.repository)


@dataclass(frozen=True, slots=True)
class TargetSettings:
    """What an admin may change on an existing target (v1.3): when it runs and what it keeps."""

    schedule: str
    quiet_window: str | None
    retention: Retention

    def __post_init__(self) -> None:
        parse_schedule(self.schedule)  # InvalidScheduleError
        parse_window(self.quiet_window)


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
    key_saved_at: datetime | None = None  # None: nobody confirmed a copy of the key exists
    mirror_path: str | None = None  # the Proton Drive folder holding an off-site copy

    @property
    def kind(self) -> TargetKind:
        return target_kind(self.repository)

    @property
    def parsed_schedule(self) -> Schedule:
        return parse_schedule(self.schedule)

    @property
    def settings(self) -> TargetSettings:
        return TargetSettings(self.schedule, self.quiet_window, self.retention)


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
    last_proven_at: datetime | None = None  # the last restore test that matched every hash
    restore_failing: bool = False  # the last restore test did not
    last_mirror_at: datetime | None = None  # the off-site copy was last brought up to date
    mirror_error: str | None = None  # why the last copy run failed
    skipped_since: datetime | None = None  # start of the latest backup run when it is skipped
    mirror_overdue: bool = False  # the copy has no fresh success

    @property
    def mirror_failing(self) -> bool:
        return self.mirror_error is not None

    @property
    def failing(self) -> bool:
        return self.last_run is not None and self.last_run.status is BackupRunStatus.FAILED

    @property
    def key_unsaved(self) -> bool:
        return self.target.key_saved_at is None

    @property
    def needs_attention(self) -> bool:
        """Drives the warning banner: overdue, the last backup, restore test or off-site copy
        failed, or nobody confirmed a copy of the recovery key."""
        trouble = self.overdue or self.failing or self.restore_failing or self.key_unsaved
        return self.target.enabled and (trouble or self.mirror_failing)


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


# --- planning a new backup (issue 3) ---------------------------------------------------------


def size_text(size: int) -> str:
    return f"{size / GB:.1f} GB" if size >= GB else f"{round(size / MB)} MB"


@dataclass(frozen=True, slots=True)
class PlaceFacts:
    """What the machine reports about a place a backup could go."""

    free_bytes: int | None  # None: it can't tell (some cloud remotes)
    same_disk: bool = False  # the disk that holds the library
    holds_backup: bool = False  # a backup made with another key is already there
    write_error: str | None = None


@dataclass(frozen=True, slots=True)
class BackupPlan:
    library_bytes: int
    free_bytes: int | None
    problem: str | None  # set: no backup can be set up there
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.problem is None


def _problem(library_bytes: int, facts: PlaceFacts) -> str | None:
    if facts.write_error:
        return f"can't write there: {facts.write_error}"
    if facts.holds_backup:
        return "there is already a backup in this folder, made with another key: choose another"
    if facts.free_bytes is not None and facts.free_bytes < library_bytes:
        return (
            f"not enough room: the library is {size_text(library_bytes)} and only "
            f"{size_text(facts.free_bytes)} is free there "
            f"({size_text(library_bytes - facts.free_bytes)} missing)"
        )
    return None


def _warnings(library_bytes: int, facts: PlaceFacts) -> tuple[str, ...]:
    found = []
    if facts.same_disk:
        found.append(
            "this is the same disk as the library: it guards against mistakes, "
            "not against the disk failing"
        )
    if facts.free_bytes is None:
        found.append("free space there can't be checked")
    elif facts.free_bytes < library_bytes * HEADROOM:
        found.append(
            f"it fits, but with little room to grow: {size_text(facts.free_bytes)} free "
            f"for a {size_text(library_bytes)} library"
        )
    return tuple(found)


def plan_backup(library_bytes: int, facts: PlaceFacts) -> BackupPlan:
    problem = _problem(library_bytes, facts)
    warnings = () if problem else _warnings(library_bytes, facts)
    return BackupPlan(library_bytes, facts.free_bytes, problem, warnings)


def restore_proof_due(
    last_backup_success: datetime | None, last_test: BackupRun | None, now: datetime
) -> bool:
    """Is it time for a restore test? Never before a backup exists; at once after the first
    one; then weekly, or a day after a test that failed."""
    if last_backup_success is None:
        return False
    if last_test is None:
        return True
    if last_test.status is BackupRunStatus.RUNNING:
        return False
    wait = PROOF_RETRY if last_test.status is BackupRunStatus.FAILED else PROOF_EVERY
    return now - last_test.started_at >= wait


def backup_due(
    schedule: Schedule,
    last_attempt: datetime,
    now: datetime,
    window: QuietWindow | None,
    *,
    catching_up: bool,
) -> bool:
    """Is a scheduled backup due? A place that just came back after being overdue does not
    wait for its quiet window: it catches up at once."""
    return is_due(schedule, last_attempt, now, None if catching_up else window)


def probe_allowed(last_probe: datetime | None, now: datetime) -> bool:
    """May we look again for a place that was not connected? Not more often than SKIP_RETRY."""
    return last_probe is None or now - last_probe >= SKIP_RETRY


# --- is the library safe? (two healthy places) -----------------------------------------------


class Severity(StrEnum):
    ALERT = "alert"  # the photos are less safe than they should be right now
    WARNING = "warning"  # something to fix, nothing is lost yet


@dataclass(frozen=True, slots=True)
class Problem:
    severity: Severity
    message: str
    target_id: int | None = None  # None: about the library as a whole
    error_kind: ErrorKind | None = None  # what kind of failure it reports; None: not one


@dataclass(frozen=True, slots=True)
class Protection:
    places_ok: int
    places_total: int
    problems: tuple[Problem, ...]  # alerts first, then warnings, each in target order

    @property
    def protected(self) -> bool:
        return self.places_ok >= 2


def _manual_and_away(status: TargetStatus) -> bool:
    """A place on a manual schedule is never overdue, so a skipped latest run is the only
    sign that it has not been backed up."""
    return status.skipped_since is not None and status.target.parsed_schedule.every is Every.MANUAL


def _place_flags(status: TargetStatus) -> tuple[bool, ...]:
    """One flag per backup place the target provides: the repository, then its Proton copy."""
    repository = (
        status.last_success_at is not None
        and not status.overdue
        and not status.failing
        and not status.restore_failing
        and not _manual_and_away(status)
    )
    if status.target.mirror_path is None:
        return (repository,)
    copy = (
        status.last_mirror_at is not None
        and not status.mirror_overdue
        and not status.mirror_failing
    )
    return (repository, copy)


def _library_problem(places_ok: int, places_total: int) -> Problem | None:
    if places_total == 0:
        return Problem(
            Severity.WARNING,
            "No backup is set up: the photos exist only on this computer. Add two backup places.",
        )
    if places_total == 1:
        return Problem(
            Severity.WARNING,
            "Only one backup place is set up: add a second, "
            "so one lost disk is not the end of the photos.",
        )
    if places_ok < 2:
        return Problem(
            Severity.ALERT, f"Only {places_ok} of {places_total} backup places is up to date."
        )
    return None


def _lateness_problem(status: TargetStatus) -> Problem | None:
    """Why the backup is not on time, when it is not: away, or just late."""
    label, tid = status.target.label, status.target.id
    if status.skipped_since is not None and status.overdue:
        return Problem(
            Severity.WARNING,
            f"{label} has not been connected since {status.skipped_since:%d %b %Y}: "
            "connect it and the backup starts by itself.",
            tid,
            ErrorKind.UNREACHABLE,
        )
    if _manual_and_away(status):
        return Problem(
            Severity.WARNING,
            f"{label} was not connected at its last backup: connect it and run the backup again.",
            tid,
            ErrorKind.UNREACHABLE,
        )
    if status.overdue and not status.failing:
        return Problem(Severity.WARNING, f"{label}: the backup is overdue.", tid)
    return None


def _target_problems(status: TargetStatus) -> list[Problem]:
    label, tid = status.target.label, status.target.id
    found = []
    if status.failing:
        reason = status.last_run.error if status.last_run else None
        found.append(
            Problem(
                Severity.ALERT,
                f"{label}: the last backup failed: {reason or 'no reason given'}",
                tid,
                error_kind(reason) or ErrorKind.UNKNOWN,
            )
        )
    if status.restore_failing:
        found.append(
            Problem(
                Severity.ALERT,
                f"{label}: the last restore test failed. Open Backups and run it again.",
                tid,
            )
        )
    if status.mirror_failing:
        found.append(
            Problem(
                Severity.ALERT,
                f"{label}: the copy on Proton Drive failed: {status.mirror_error}",
                tid,
                error_kind(status.mirror_error),
            )
        )
    late = _lateness_problem(status)
    if late is not None:
        found.append(late)
    if status.mirror_overdue and not status.mirror_failing:
        found.append(
            Problem(
                Severity.WARNING,
                f"{label}: the copy on Proton Drive is out of date; "
                "it catches up when this computer is online.",
                tid,
            )
        )
    if status.key_unsaved:
        found.append(
            Problem(
                Severity.WARNING,
                f"{label}: the recovery key is not saved yet. "
                "Without it this backup cannot be read.",
                tid,
            )
        )
    return found


def protection(statuses: Sequence[TargetStatus]) -> Protection:
    """Are there two healthy backup places, and what is wrong with the rest? Each enabled
    target is a place; its Proton Drive copy, when it has one, is another."""
    enabled = [s for s in statuses if s.target.enabled]
    flags = [flag for s in enabled for flag in _place_flags(s)]
    places_ok, places_total = sum(flags), len(flags)
    problems = [p for p in [_library_problem(places_ok, places_total)] if p]
    for status in enabled:
        problems.extend(_target_problems(status))
    problems.sort(key=lambda p: p.severity is Severity.WARNING)  # stable: alerts first
    return Protection(places_ok, places_total, tuple(problems))
