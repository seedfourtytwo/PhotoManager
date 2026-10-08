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
    BackupPlan,
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    PlaceFacts,
    RestoreCheck,
    RestoreTestReport,
    Retention,
    RunKind,
    RunOutcome,
    TargetKind,
    TargetSettings,
    TargetStatus,
    plan_backup,
    restore_proof_due,
    size_text,
)
from photo_assistant.domain.library_paths import nested_or_same
from photo_assistant.domain.remote_source import PROTON_PHOTOS, RemoteConfig, RemoteConfigError
from photo_assistant.domain.schedule import is_due, is_overdue, next_run, parse_window
from photo_assistant.ports import Clock, Hasher
from photo_assistant.ports.backup import (
    AssetFile,
    BackupEngine,
    BackupError,
    BackupPlaces,
    BackupStore,
    DatabaseSnapshotter,
    Disk,
    JobQueue,
    KeyVault,
    MirrorReport,
    PasswordFileError,
    RepositoryMirror,
    RepositoryRef,
)

log = logging.getLogger(__name__)

BACKUP_JOB = "backup_run"
RESTORE_TEST_JOB = "backup_restore_test"
BACKUP_DUE_JOB = "backup_due"  # queued by the periodic check: runs every target that is due
MIRROR_JOB = "backup_mirror"  # bring one target's off-site copy up to date
LONG_JOBS = frozenset({BACKUP_JOB, RESTORE_TEST_JOB, BACKUP_DUE_JOB, MIRROR_JOB})
MIRROR_STATE_DIR = "mirror"  # in the data root, outside what a backup contains
DB_SNAPSHOT_PATH = f"{DB_SNAPSHOT_DIR}/{DB_SNAPSHOT_FILE}"
REPOSITORY_FOLDER = "photo-assistant-backup"  # a guided setup always makes its own folder
RCLONE_PREFIX = "rclone:"

Handler = Callable[[dict[str, object]], object]


class UnknownTargetError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class RecoverySheet:
    """Everything needed to read a backup without this machine: keep it somewhere else."""

    label: str
    repository: str
    key: str


def repository_in(place: str) -> str:
    """The repository a guided setup uses inside ``place``: a folder path, or
    ``rclone:<remote>:<folder>``. Raises ValueError for anything else."""
    place = place.strip()
    if place.startswith(RCLONE_PREFIX):
        remote, colon, folder = place.removeprefix(RCLONE_PREFIX).partition(":")
        if not remote or not colon:
            raise ValueError("a cloud location looks like rclone:<name>:<folder>")
        inside = f"{folder.rstrip('/')}/" if folder.strip("/") else ""
        return f"{RCLONE_PREFIX}{remote}:{inside}{REPOSITORY_FOLDER}"
    if not Path(place).is_absolute():
        raise ValueError("a local backup location must be an absolute path")
    return str(Path(place) / REPOSITORY_FOLDER)


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


def _files(count: int, word: str) -> str:
    return f"{count} {word} file{'' if count == 1 else 's'}"


def _mirror_summary(report: MirrorReport) -> str:
    sent = f"{_files(report.uploaded, 'new')} sent ({size_text(report.bytes_sent)})"
    return f"{sent}, {_files(report.removed, 'old')} removed"


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
        places: BackupPlaces | None = None,
        vault: KeyVault | None = None,
        mirror: RepositoryMirror | None = None,
        *,
        database_integrity: Callable[[Path], str],
    ) -> None:
        """``database_integrity``: the probe ``just doctor`` uses (SystemProbe): "ok", or what
        is wrong with the SQLite file at that path."""
        if config.scratch_dir is not None and _inside(config.scratch_dir, config.data_root):
            raise ValueError("the restore-test folder must be outside the library")
        self._store = store
        self._engine = engine
        self._snapshotter = snapshotter
        self._hasher = hasher
        self._clock = clock
        self._config = config
        self._queue = queue
        self._places = places
        self._vault = vault
        self._database_integrity = database_integrity
        self._mirror = mirror
        self._lock = threading.Lock()  # one run at a time per process; restic locks the repo

    # --- targets ---------------------------------------------------------------------------

    def add_target(self, new: NewBackupTarget, *, own_key_only: bool = False) -> BackupTarget:
        """``own_key_only`` (requests over HTTP): the password file must be one of the key
        vault's own files. The recovery sheet shows that file, so a free path would let a
        browser session read any file; the command line may still point anywhere."""
        if own_key_only and not self._need_vault().holds(Path(new.password_file)):
            raise ValueError(
                "the password file must be a key file in this app's key folder; for a file "
                "elsewhere on the server use the command line (just backup add)"
            )
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

    # --- guided setup (issue 3) ------------------------------------------------------------

    def places(self) -> tuple[list[Disk], list[str]]:
        """Plugged-in disks and rclone remotes a backup could go to."""
        found = self._need_places()
        return found.disks(), found.remotes()

    def disks(self) -> list[Disk]:
        """Plugged-in external disks (also the starting points when browsing for a folder)."""
        return self._need_places().disks()

    def library_bytes(self) -> int:
        return self._store.library_bytes()

    def plan(self, place: str) -> tuple[str, BackupPlan]:
        """The repository a setup in ``place`` would use, and whether it can go ahead.
        Changes nothing."""
        size = self._store.library_bytes()
        try:
            repository = repository_in(place)
            if not repository.startswith(RCLONE_PREFIX):
                self._validate_local_repository(Path(repository))
        except ValueError as exc:
            return place, BackupPlan(size, None, str(exc))
        facts: PlaceFacts = self._need_places().facts(repository, self._config.data_root)
        return repository, plan_backup(size, facts)

    def set_up(
        self,
        label: str,
        place: str,
        schedule: str = "daily 02:30",
        retention: Retention | None = None,
    ) -> tuple[BackupTarget, str]:
        """A new target with a key made here, and its first backup queued. Returns the key:
        the owner must keep a copy (``confirm_key_saved``). Raises ValueError with the reason
        when the place won't do or the name is taken."""
        vault = self._need_vault()
        repository, plan = self.plan(place)
        if plan.problem:
            raise ValueError(plan.problem)
        label = label.strip()
        if any(t.label.casefold() == label.casefold() for t in self._store.list_targets()):
            raise ValueError(f"a backup target named {label!r} already exists")
        keep = retention or Retention()
        # checks the name and the schedule before a key exists: a refused setup leaves no key
        NewBackupTarget(label, repository, "/unset", schedule, None, keep)
        key_file, key = vault.create()
        try:
            new = NewBackupTarget(label, repository, str(key_file), schedule, None, keep, False)
            target = self.add_target(new)
        except BaseException:
            vault.discard(key_file)
            raise
        if self._queue is not None:
            self._queue.enqueue(BACKUP_JOB, {"target_id": target.id})
        return target, key

    def recovery(self, target_id: int) -> RecoverySheet:
        target = self.target(target_id)
        vault, key_file = self._need_vault(), Path(target.password_file)
        if not vault.holds(key_file):  # never read a file the vault doesn't own
            raise PasswordFileError(
                "this backup's password file was chosen on the command line, so it is not "
                f"shown here: read {key_file} on the server"
            )
        return RecoverySheet(target.label, target.repository, vault.read(key_file))

    def confirm_key_saved(self, target_id: int) -> None:
        """The owner says a copy of the key exists outside this machine. The first time counts."""
        if self.target(target_id).key_saved_at is None:
            self._store.mark_key_saved(target_id, self._clock.now())

    def _need_places(self) -> BackupPlaces:
        if self._places is None:
            raise RuntimeError("no backup places configured")
        return self._places

    def _need_vault(self) -> KeyVault:
        if self._vault is None:
            raise RuntimeError("no key vault configured for backups")
        return self._vault

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

    def change_settings(self, target_id: int, settings: TargetSettings) -> BackupTarget:
        """New schedule, quiet window and retention; the next run follows them at once."""
        self.target(target_id)
        self._store.set_target_settings(target_id, settings)
        return self.target(target_id)

    def recover_interrupted(self) -> int:
        """Call once at startup, before the worker: runs left 'running' were cut off."""
        return self._store.recover_interrupted_runs(self._clock.now())

    def runs(self, target_id: int, limit: int = 50) -> list[BackupRun]:
        self.target(target_id)
        return self._store.list_runs(target_id, limit)

    # --- running ---------------------------------------------------------------------------

    def run_now(self, target_id: int) -> BackupRun:
        target = self.target(target_id)
        run = self._record(target, RunKind.BACKUP, lambda: self._backup(target))
        if run.status is BackupRunStatus.SUCCEEDED:
            self.mirror_now(target_id)
        return run

    # --- the off-site copy (issue 14) --------------------------------------------------------

    def set_mirror(self, target_id: int, mirror_path: str | None) -> BackupTarget:
        """Keep a copy of this backup in a Proton Drive folder (None: stop). The first copy
        is queued at once when there is a backup to copy."""
        target = self.target(target_id)
        if mirror_path is not None:
            if self._mirror is None:
                raise ValueError("a copy on Proton Drive is not available on this machine")
            if target.kind is not TargetKind.LOCAL:
                raise ValueError("only a backup in a folder or disk of this machine can be copied")
            try:
                if mirror_path == PROTON_PHOTOS:
                    raise RemoteConfigError
                RemoteConfig.proton(mirror_path)
            except RemoteConfigError as exc:
                raise ValueError("choose a folder in My files on Proton Drive") from exc
        self._store.set_target_mirror(target_id, mirror_path)
        has_backup = self._store.last_run(target_id, RunKind.BACKUP, succeeded_only=True)
        if mirror_path is not None and has_backup is not None and self._queue is not None:
            self._queue.enqueue(MIRROR_JOB, {"target_id": target_id})
        return self.target(target_id)

    def mirror_now(self, target_id: int) -> BackupRun | None:
        """Bring the off-site copy up to date; None when this target has none."""
        target = self.target(target_id)
        mirror, remote = self._mirror, target.mirror_path
        if mirror is None or remote is None:
            return None
        state = self._config.data_root / MIRROR_STATE_DIR / f"{target.id}.json"

        def work() -> RunOutcome:
            report = mirror.mirror(Path(target.repository), remote, state)
            return RunOutcome(BackupRunStatus.SUCCEEDED, details=_mirror_summary(report))

        return self._record(target, RunKind.MIRROR, work)

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
        """Called periodically: run every enabled target whose schedule says so, then prove
        the backups whose restore test is due. Returns the backup runs."""
        now = self._local(self._clock.now())
        done = []
        for target in self._store.list_targets():
            if target.enabled and self._is_due(target, now):
                done.append(self.run_now(target.id))
        for target in self._store.list_targets():
            if target.enabled:
                self._prove_if_due(target)
        return done

    def _prove_if_due(self, target: BackupTarget) -> None:
        """The recovery guarantee: restore a sample after the first backup, then weekly."""
        success = self._store.last_run(target.id, RunKind.BACKUP, succeeded_only=True)
        last_test = self._store.last_run(target.id, RunKind.RESTORE_TEST)
        proven_from = (success.finished_at or success.started_at) if success else None
        if restore_proof_due(proven_from, last_test, self._clock.now()):
            self.restore_test(target.id)

    def _run_and_prove(self, target_id: int) -> BackupRun:
        run = self.run_now(target_id)
        if run.status is BackupRunStatus.SUCCEEDED:
            self._prove_if_due(self.target(target_id))
        return run

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
        # The snapshot exists from here on: trouble while tidying up (a locked repository, a
        # network blip) is reported in the details, never as a failed backup.
        problems = []
        try:
            self._engine.forget(repo, target.retention)
        except (BackupError, OSError) as exc:
            problems.append(f"pruning failed: {_message(exc)}")
        repo_bytes = None
        try:
            repo_bytes = self._engine.repository_size(repo)
        except (BackupError, OSError) as exc:
            problems.append(f"measuring the backup failed: {_message(exc)}")
        if problems:
            log.warning("backup written, tidying up failed", extra={"target": target.label})
        return RunOutcome(
            BackupRunStatus.SUCCEEDED,
            snapshot_id=summary.snapshot_id,
            bytes_added=summary.bytes_added,
            files_new=summary.files_new,
            files_changed=summary.files_changed,
            repo_bytes=repo_bytes,
            details="; ".join(["snapshot ok", *problems]) if problems else None,
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
        if not restored.is_file() or restored.stat().st_size == 0:
            reason = "database snapshot missing from the backup"
            return RestoreCheck(DB_SNAPSHOT_PATH, False, reason)
        verdict = self._database_integrity(restored)
        if verdict != "ok":
            return RestoreCheck(DB_SNAPSHOT_PATH, False, f"database snapshot is damaged: {verdict}")
        return RestoreCheck(DB_SNAPSHOT_PATH, True)

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
        window = parse_window(target.quiet_window)
        upcoming = (
            next_run(schedule, self._last_attempt(target), window) if target.enabled else None
        )
        success_at = (success.finished_at or success.started_at) if success else None
        overdue = is_overdue(
            schedule,
            self._local(success_at) if success_at else None,
            self._local(target.created_at),
            now,
            window,
        )
        test = self._store.last_run(target.id, RunKind.RESTORE_TEST)
        proven = self._store.last_run(target.id, RunKind.RESTORE_TEST, succeeded_only=True)
        copy = self._store.last_run(target.id, RunKind.MIRROR) if target.mirror_path else None
        copied = (
            self._store.last_run(target.id, RunKind.MIRROR, succeeded_only=True)
            if target.mirror_path
            else None
        )
        copy_failed = copy is not None and copy.status is BackupRunStatus.FAILED
        return TargetStatus(
            target=target,
            last_success_at=success_at,
            last_run=last,
            repo_bytes=success.repo_bytes if success else None,
            next_run_at=self._aware(upcoming) if upcoming else None,
            overdue=overdue,
            last_proven_at=(proven.finished_at or proven.started_at) if proven else None,
            restore_failing=test is not None and test.status is BackupRunStatus.FAILED,
            last_mirror_at=(copied.finished_at or copied.started_at) if copied else None,
            mirror_error=(copy.error or "the copy failed") if copy and copy_failed else None,
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
            BACKUP_JOB: lambda payload: self._run_and_prove(int(str(payload["target_id"]))),
            RESTORE_TEST_JOB: lambda payload: self.restore_test(int(str(payload["target_id"]))),
            BACKUP_DUE_JOB: lambda payload: self.run_due(),
            MIRROR_JOB: lambda payload: self.mirror_now(int(str(payload["target_id"]))),
        }
