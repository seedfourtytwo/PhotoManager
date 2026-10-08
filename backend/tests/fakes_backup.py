"""In-memory fakes for the backup ports; the contract tests run the same suite on the real ones."""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from photo_assistant.domain.backup import (
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    PlaceFacts,
    Retention,
    RunKind,
    RunOutcome,
    TargetSettings,
)
from photo_assistant.ports.backup import (
    AssetFile,
    BackupError,
    Disk,
    MirrorReport,
    PasswordFileError,
    RepositoryRef,
    SnapshotInfo,
    SnapshotSummary,
)


class InMemoryBackupStore:
    def __init__(self, assets: Sequence[tuple[AssetFile, datetime]] = ()) -> None:
        self.targets: dict[int, BackupTarget] = {}
        self.runs: dict[int, BackupRun] = {}
        self.assets = list(assets)
        self.asset_bytes = 0
        self._ids = itertools.count(1)

    def add_target(self, target: NewBackupTarget, created_at: datetime) -> BackupTarget:
        if any(t.label == target.label for t in self.targets.values()):
            raise ValueError(f"a backup target named {target.label!r} already exists")
        new = BackupTarget(
            id=next(self._ids),
            label=target.label,
            repository=target.repository,
            password_file=target.password_file,
            schedule=target.schedule,
            quiet_window=target.quiet_window,
            retention=target.retention,
            enabled=True,
            created_at=created_at,
            key_saved_at=created_at if target.key_saved else None,
        )
        self.targets[new.id] = new
        return new

    def mark_key_saved(self, target_id: int, at: datetime) -> None:
        if target_id in self.targets:
            self.targets[target_id] = replace(self.targets[target_id], key_saved_at=at)

    def library_bytes(self) -> int:
        return self.asset_bytes

    def get_target(self, target_id: int) -> BackupTarget | None:
        return self.targets.get(target_id)

    def list_targets(self) -> list[BackupTarget]:
        return [self.targets[k] for k in sorted(self.targets)]

    def set_target_enabled(self, target_id: int, enabled: bool) -> None:
        if target_id in self.targets:
            self.targets[target_id] = replace(self.targets[target_id], enabled=enabled)

    def set_target_mirror(self, target_id: int, mirror_path: str | None) -> None:
        if target_id in self.targets:
            self.targets[target_id] = replace(self.targets[target_id], mirror_path=mirror_path)

    def set_target_settings(self, target_id: int, settings: TargetSettings) -> None:
        if target_id in self.targets:
            self.targets[target_id] = replace(
                self.targets[target_id],
                schedule=settings.schedule,
                quiet_window=settings.quiet_window,
                retention=settings.retention,
            )

    def start_run(self, target_id: int, kind: RunKind, started_at: datetime) -> int:
        run_id = next(self._ids)
        self.runs[run_id] = BackupRun(run_id, target_id, kind, BackupRunStatus.RUNNING, started_at)
        return run_id

    def finish_run(self, run_id: int, finished_at: datetime, outcome: RunOutcome) -> None:
        run = self.runs[run_id]
        self.runs[run_id] = BackupRun(
            run.id,
            run.target_id,
            run.kind,
            outcome.status,
            run.started_at,
            finished_at,
            outcome.snapshot_id,
            outcome.bytes_added,
            outcome.files_new,
            outcome.files_changed,
            outcome.repo_bytes,
            outcome.error,
            outcome.details,
        )

    def get_run(self, run_id: int) -> BackupRun | None:
        return self.runs.get(run_id)

    def list_runs(self, target_id: int, limit: int = 50) -> list[BackupRun]:
        runs = [r for r in self.runs.values() if r.target_id == target_id]
        return sorted(runs, key=lambda r: r.id, reverse=True)[:limit]

    def last_run(
        self, target_id: int, kind: RunKind, *, succeeded_only: bool = False
    ) -> BackupRun | None:
        for run in self.list_runs(target_id, limit=10_000):
            if run.kind is kind and (not succeeded_only or run.status is BackupRunStatus.SUCCEEDED):
                return run
        return None

    def recover_interrupted_runs(self, now: datetime) -> int:
        stuck = [r for r in self.runs.values() if r.status is BackupRunStatus.RUNNING]
        for run in stuck:
            self.finish_run(run.id, now, RunOutcome(BackupRunStatus.FAILED, error="interrupted"))
        return len(stuck)

    def sample_assets(self, count: int, imported_before: datetime) -> list[AssetFile]:
        return [a for a, when in self.assets if when <= imported_before][:count]


@dataclass
class FakeEngine:
    """Remembers what it was asked; 'restores' by copying from the data root it backed up."""

    fail: dict[str, Exception] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    snapshots: list[SnapshotInfo] = field(default_factory=list)
    backed_up: list[tuple[Path, tuple[str, ...]]] = field(default_factory=list)
    retention: Retention | None = None
    corrupt: set[str] = field(default_factory=set)
    now: datetime = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]

    def ensure_repository(self, repo: RepositoryRef) -> bool:
        self._call("ensure")
        return False

    def backup(self, repo: RepositoryRef, root: Path, folders: Sequence[str]) -> SnapshotSummary:
        self._call("backup")
        self.backed_up.append((root, tuple(folders)))
        snap = SnapshotInfo(f"{len(self.snapshots) + 1:064x}", self.now + timedelta(minutes=1))
        self.snapshots.append(snap)
        return SnapshotSummary(snap.snapshot_id, 3, 0, 1234, 5678)

    def forget(self, repo: RepositoryRef, retention: Retention) -> None:
        self._call("forget")
        self.retention = retention

    def check(self, repo: RepositoryRef, read_data_subset: str | None = None) -> None:
        self._call(f"check {read_data_subset}")

    def latest_snapshot(self, repo: RepositoryRef) -> SnapshotInfo | None:
        self._call("latest")
        return self.snapshots[-1] if self.snapshots else None

    def restore(
        self, repo: RepositoryRef, snapshot_id: str, paths: Sequence[str], target: Path
    ) -> None:
        self._call("restore")
        root = self.backed_up[-1][0]
        for relative in paths:
            source = root / relative
            if not source.is_file():
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            destination.write_bytes(b"bitrot" + data if relative in self.corrupt else data)

    def repository_size(self, repo: RepositoryRef) -> int:
        self._call("size")
        return 99_000


@dataclass
class FakePlaces:
    """The machine as the test describes it; ``asked`` records what was looked up."""

    found_disks: list[Disk] = field(default_factory=list)
    found_remotes: list[str] = field(default_factory=list)
    by_repository: dict[str, PlaceFacts] = field(default_factory=dict)
    default: PlaceFacts = field(default_factory=lambda: PlaceFacts(free_bytes=500 * 1000**3))
    asked: list[str] = field(default_factory=list)

    def disks(self) -> list[Disk]:
        return list(self.found_disks)

    def remotes(self) -> list[str]:
        return list(self.found_remotes)

    def facts(self, repository: str, data_root: Path) -> PlaceFacts:
        self.asked.append(repository)
        return self.by_repository.get(repository, self.default)


class FakeVault:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._count = itertools.count(1)

    def create(self) -> tuple[Path, str]:
        n = next(self._count)
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"key-{n}"
        path.write_text(f"secret-{n}\n")
        return path, f"secret-{n}"

    def read(self, key_file: Path) -> str:
        if not key_file.is_file():
            raise PasswordFileError(f"the key file is gone: {key_file}")
        return key_file.read_text().strip()

    def discard(self, key_file: Path) -> None:
        key_file.unlink(missing_ok=True)


class FakeSnapshotter:
    def __init__(self, fail: BackupError | None = None) -> None:
        self.fail = fail
        self.taken: list[Path] = []

    def snapshot(self, destination: Path) -> None:
        if self.fail:
            raise self.fail
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"SQLite format 3\x00 fake")
        self.taken.append(destination)


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, dict[str, object]]] = []

    def enqueue(self, kind: str, payload: dict[str, object]) -> int:
        self.jobs.append((kind, payload))
        return len(self.jobs)


class SteppingClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current


class FakeMirror:
    """Remembers what it was asked to copy where; fails on demand."""

    def __init__(self) -> None:
        self.fail: BackupError | None = None
        self.calls: list[tuple[Path, str, Path]] = []

    def mirror(self, repository: Path, remote_folder: str, state_file: Path) -> MirrorReport:
        self.calls.append((repository, remote_folder, state_file))
        if self.fail:
            raise self.fail
        return MirrorReport(uploaded=2, removed=1, bytes_sent=5_000_000)
