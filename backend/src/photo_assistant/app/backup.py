"""Backups (FEATURES 9b): run a target now, run what is due, report status, test a restore.

Guarantees (tests/app/test_backup.py, tests/adapters/test_restic_backup.py):
- the library is only ever read: restic reads the data root, restores go to a temp folder
  outside it, and a failed run changes nothing but its own ``backup_run`` row;
- the database is never copied live: a consistent snapshot is written first (online backup API);
- every run, successful or not, is recorded with a reason the owner can act on.
"""

import logging
import shutil
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path

from photo_assistant.domain.backup import (
    BACKUP_FOLDERS,
    DB_SNAPSHOT_DIR,
    DB_SNAPSHOT_FILE,
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    RestoreCheck,
    RestoreTestReport,
    RunKind,
    RunOutcome,
    TargetKind,
    TargetStatus,
)
from photo_assistant.domain.library_paths import nested_or_same
from photo_assistant.domain.schedule import is_due, is_overdue, next_run, parse_window
from photo_assistant.ports import Clock, Hasher
from photo_assistant.ports.backup import (
    AssetFile,
    BackupEngine,
    BackupError,
    BackupStore,
    DatabaseSnapshotter,
    JobQueue,
    RepositoryRef,
)

log = logging.getLogger(__name__)

BACKUP_JOB = "backup_run"
RESTORE_TEST_JOB = "backup_restore_test"
BACKUP_DUE_JOB = "backup_due"  # queued by the periodic check: runs every target that is due
LONG_JOBS = frozenset({BACKUP_JOB, RESTORE_TEST_JOB, BACKUP_DUE_JOB})
DB_SNAPSHOT_PATH = f"{DB_SNAPSHOT_DIR}/{DB_SNAPSHOT_FILE}"

Handler = Callable[[dict[str, object]], object]


class UnknownTargetError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class BackupConfig:
    data_root: Path
    restore_sample: int = 20
    scratch_dir: Path | None = None  # where restore tests unpack; None = the system temp dir
    local_tz: tzinfo | None = None  # schedules are local wall-clock; None = this machine's zone
    # the folders the library imports from: a local repository may not overlap one (QA A5)
    source_roots: Callable[[], Sequence[Path]] = field(default=lambda: ())


def _inside(a: Path, b: Path) -> bool:
    """True if either path contains the other (after resolving symlinks)."""
    return nested_or_same(a.expanduser().resolve(), b.expanduser().resolve())


def _message(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


class BackupService:
    def __init__(
        self,
        store: BackupStore,
        engine: BackupEngine,
        snapshotter: DatabaseSnapshotter,
        hasher: Hasher,
        clock: Clock,
        config: BackupConfig,
        queue: JobQueue | None = None,
    ) -> None:
        if config.scratch_dir is not None and _inside(config.scratch_dir, config.data_root):
            raise ValueError("the restore-test folder must be outside the library")
        self._store = store
        self._engine = engine
        self._snapshotter = snapshotter
        self._hasher = hasher
        self._clock = clock
        self._config = config
        self._queue = queue
        self._lock = threading.Lock()  # one run at a time per process; restic locks the repo

    # --- targets ---------------------------------------------------------------------------

    def add_target(self, new: NewBackupTarget) -> BackupTarget:
        self._validate_locations(new)
        return self._store.add_target(new, self._clock.now())

    def _validate_locations(self, new: NewBackupTarget) -> None:
        password = Path(new.password_file)
        if not password.is_absolute():
            raise ValueError("the password file path must be absolute")
        if _inside(password, self._config.data_root):
            raise ValueError("keep the password file outside the library, e.g. ~/.config")
        if not password.is_file():
            raise ValueError(f"password file not found: {password} (create it first)")
        if new.kind is TargetKind.LOCAL:
            self._validate_local_repository(Path(new.repository))

    def _validate_local_repository(self, repo: Path) -> None:
        if not repo.is_absolute():
            raise ValueError("a local backup location must be an absolute path")
        if _inside(repo, self._config.data_root):
            raise ValueError("a backup cannot live inside the library, or contain it")
        for root in self._config.source_roots():
            if _inside(repo, root):
                raise ValueError(
                    f"a backup cannot live inside a source folder, or contain one: {root}"
                )

    def repository_overlaps(self, folder: Path) -> bool:
        """Is ``folder`` inside a local backup repository, or does it contain one? (A source
        there would import restic's files, and restic would write into a source.)"""
        return any(
            _inside(folder, Path(t.repository))
            for t in self._store.list_targets()
            if t.kind is TargetKind.LOCAL
        )

    def targets(self) -> list[BackupTarget]:
        return self._store.list_targets()

    def target(self, target_id: int) -> BackupTarget:
        found = self._store.get_target(target_id)
        if found is None:
            raise UnknownTargetError(f"no backup target {target_id}")
        return found

    def set_enabled(self, target_id: int, enabled: bool) -> None:
        self.target(target_id)
        self._store.set_target_enabled(target_id, enabled)

    def recover_interrupted(self) -> int:
        """Call once at startup, before the worker: runs left 'running' were cut off."""
        return self._store.recover_interrupted_runs(self._clock.now())

    def runs(self, target_id: int, limit: int = 50) -> list[BackupRun]:
        self.target(target_id)
        return self._store.list_runs(target_id, limit)

    # --- running ---------------------------------------------------------------------------

    def run_now(self, target_id: int) -> BackupRun:
        target = self.target(target_id)
        return self._record(target, RunKind.BACKUP, lambda: self._backup(target))

    def check(self, target_id: int, read_data_subset: str | None = None) -> BackupRun:
        target = self.target(target_id)

        def work() -> RunOutcome:
            self._engine.check(self._repo(target), read_data_subset)
            read = f"; read {read_data_subset} of the data" if read_data_subset else ""
            return RunOutcome(BackupRunStatus.SUCCEEDED, details=f"repository is healthy{read}")

        return self._record(target, RunKind.CHECK, work)

    def restore_test(self, target_id: int, sample_size: int | None = None) -> BackupRun:
        target = self.target(target_id)
        count = self._config.restore_sample if sample_size is None else sample_size

        def work() -> RunOutcome:
            report = self._restore_sample(target, count)
            status = BackupRunStatus.SUCCEEDED if report.ok else BackupRunStatus.FAILED
            error = None if report.ok else report.summary()
            return RunOutcome(
                status, snapshot_id=report.snapshot_id, details=report.summary(), error=error
            )

        return self._record(target, RunKind.RESTORE_TEST, work)

    def run_due(self) -> list[BackupRun]:
        """Called periodically: run every enabled target whose schedule says so."""
        now = self._local(self._clock.now())
        done = []
        for target in self._store.list_targets():
            if target.enabled and self._is_due(target, now):
                done.append(self.run_now(target.id))
        return done

    def _is_due(self, target: BackupTarget, now: datetime) -> bool:
        window = parse_window(target.quiet_window)
        return is_due(target.parsed_schedule, self._last_attempt(target), now, window)

    def _last_attempt(self, target: BackupTarget) -> datetime:
        last = self._store.last_run(target.id, RunKind.BACKUP)
        return self._local(last.started_at if last else target.created_at)

    def _record(
        self, target: BackupTarget, kind: RunKind, work: Callable[[], RunOutcome]
    ) -> BackupRun:
        with self._lock:
            run_id = self._store.start_run(target.id, kind, self._clock.now())
            try:
                outcome = work()
            except (BackupError, OSError) as exc:
                log.warning("backup %s failed", kind.value, extra={"target": target.label})
                outcome = RunOutcome(BackupRunStatus.FAILED, error=_message(exc))
            except BaseException as exc:
                failed = RunOutcome(BackupRunStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
                self._store.finish_run(run_id, self._clock.now(), failed)
                raise
            self._store.finish_run(run_id, self._clock.now(), outcome)
            run = self._store.get_run(run_id)
            assert run is not None
            return run

    def _repo(self, target: BackupTarget) -> RepositoryRef:
        return RepositoryRef(target.repository, Path(target.password_file))

    def _backup(self, target: BackupTarget) -> RunOutcome:
        repo = self._repo(target)
        root = self._config.data_root
        self._engine.ensure_repository(repo)
        self._snapshotter.snapshot(root / DB_SNAPSHOT_DIR / DB_SNAPSHOT_FILE)
        summary = self._engine.backup(repo, root, BACKUP_FOLDERS)
        self._engine.forget(repo, target.retention)
        return RunOutcome(
            BackupRunStatus.SUCCEEDED,
            snapshot_id=summary.snapshot_id,
            bytes_added=summary.bytes_added,
            files_new=summary.files_new,
            files_changed=summary.files_changed,
            repo_bytes=self._engine.repository_size(repo),
        )

    # --- restore test (FEATURES 9b.8) ------------------------------------------------------

    def _restore_sample(self, target: BackupTarget, count: int) -> RestoreTestReport:
        repo = self._repo(target)
        latest = self._engine.latest_snapshot(repo)
        if latest is None:
            return RestoreTestReport(None, ())
        sample = self._store.sample_assets(count, latest.time)
        paths = [DB_SNAPSHOT_PATH, *(a.library_path for a in sample)]
        scratch = Path(tempfile.mkdtemp(prefix="pa-restore-test-", dir=self._config.scratch_dir))
        try:
            self._engine.restore(repo, latest.snapshot_id, paths, scratch)
            checks = [self._check_database(scratch), *(self._check(scratch, a) for a in sample)]
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return RestoreTestReport(latest.snapshot_id, tuple(checks))

    def _check_database(self, scratch: Path) -> RestoreCheck:
        restored = scratch / DB_SNAPSHOT_PATH
        if restored.is_file() and restored.stat().st_size > 0:
            return RestoreCheck(DB_SNAPSHOT_PATH, True)
        return RestoreCheck(DB_SNAPSHOT_PATH, False, "database snapshot missing from the backup")

    def _check(self, scratch: Path, asset: AssetFile) -> RestoreCheck:
        restored = scratch / asset.library_path
        if not restored.is_file():
            return RestoreCheck(asset.library_path, False, "missing from the backup")
        if self._hasher.hash_file(restored) != asset.content_hash:
            return RestoreCheck(asset.library_path, False, "restored bytes do not match the hash")
        return RestoreCheck(asset.library_path, True)

    # --- status (FEATURES 9b.7) ------------------------------------------------------------

    def status(self) -> list[TargetStatus]:
        now = self._local(self._clock.now())
        return [self._status(t, now) for t in self._store.list_targets()]

    def _status(self, target: BackupTarget, now: datetime) -> TargetStatus:
        last = self._store.last_run(target.id, RunKind.BACKUP)
        success = self._store.last_run(target.id, RunKind.BACKUP, succeeded_only=True)
        schedule = target.parsed_schedule
        upcoming = None
        if target.enabled:
            upcoming = next_run(
                schedule, self._last_attempt(target), parse_window(target.quiet_window)
            )
        success_at = (success.finished_at or success.started_at) if success else None
        overdue = is_overdue(
            schedule,
            self._local(success_at) if success_at else None,
            self._local(target.created_at),
            now,
        )
        return TargetStatus(
            target=target,
            last_success_at=success_at,
            last_run=last,
            repo_bytes=success.repo_bytes if success else None,
            next_run_at=self._aware(upcoming) if upcoming else None,
            overdue=overdue,
        )

    def _local(self, moment: datetime) -> datetime:
        return moment.astimezone(self._config.local_tz).replace(tzinfo=None)

    def _aware(self, local: datetime) -> datetime:
        if self._config.local_tz is None:
            return local.astimezone()  # naive = this machine's local time
        return local.replace(tzinfo=self._config.local_tz)

    # --- worker integration ----------------------------------------------------------------

    def queue_run(self, target_id: int) -> int:
        return self._enqueue(BACKUP_JOB, target_id)

    def queue_restore_test(self, target_id: int) -> int:
        return self._enqueue(RESTORE_TEST_JOB, target_id)

    def _enqueue(self, kind: str, target_id: int) -> int:
        self.target(target_id)
        if self._queue is None:
            raise RuntimeError("no job queue configured for backups")
        return self._queue.enqueue(kind, {"target_id": target_id})

    def job_handlers(self) -> dict[str, Handler]:
        """Register these with the Worker: manual runs go through the job queue."""
        return {
            BACKUP_JOB: lambda payload: self.run_now(int(str(payload["target_id"]))),
            RESTORE_TEST_JOB: lambda payload: self.restore_test(int(str(payload["target_id"]))),
            BACKUP_DUE_JOB: lambda payload: self.run_due(),
        }
