"""BackupStore contract (fake and SQLite) and the database snapshotter."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_backup_store import SqliteBackupStore
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.adapters.sqlite_snapshot import SqliteSnapshotter, open_read_only
from photo_assistant.domain.backup import (
    BackupRunStatus,
    NewBackupTarget,
    Retention,
    RunKind,
    RunOutcome,
    TargetSettings,
)
from photo_assistant.ports.backup import AssetFile, BackupError, BackupStore
from tests.factories import new_asset
from tests.fakes_backup import InMemoryBackupStore

T0 = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
OLD, NEW = T0 - timedelta(days=2), T0 + timedelta(days=2)


def _sqlite() -> BackupStore:
    conn = open_database(":memory:")
    repo = SqliteRepository(conn)
    repo.add_asset(new_asset(1), OLD)
    repo.add_asset(new_asset(2), OLD)
    repo.add_asset(new_asset(3), NEW)
    return SqliteBackupStore(conn)


def _fake() -> BackupStore:
    def asset(n: int) -> AssetFile:
        return AssetFile(n, f"{n:064x}", f"originals/2020/01/{n:064x}.jpg")

    fake = InMemoryBackupStore([(asset(1), OLD), (asset(2), OLD), (asset(3), NEW)])
    fake.asset_bytes = 1001 + 1002 + 1003
    return fake


@pytest.fixture(params=[_fake, _sqlite], ids=["fake", "sqlite"])
def store(request: pytest.FixtureRequest) -> Iterator[BackupStore]:
    factory: Callable[[], BackupStore] = request.param
    yield factory()


def _target(label: str = "Disk", **extra: object) -> NewBackupTarget:
    return NewBackupTarget(label, "/media/c/Backup/photos", "/home/c/.config/pa/pw", **extra)  # type: ignore[arg-type]


def test_targets_round_trip(store: BackupStore) -> None:
    created = store.add_target(
        _target(
            schedule="weekly sun 03:00", quiet_window="22:00-06:00", retention=Retention(1, 2, 3)
        ),
        T0,
    )
    assert store.get_target(created.id) == created
    assert created.kind.value == "local" and created.enabled
    assert (created.schedule, created.quiet_window) == ("weekly sun 03:00", "22:00-06:00")
    assert created.retention == Retention(1, 2, 3) and created.created_at == T0
    with pytest.raises(ValueError, match="already exists"):
        store.add_target(_target(), T0)
    store.set_target_enabled(created.id, False)
    assert [t.enabled for t in store.list_targets()] == [False]
    assert store.get_target(999) is None


def test_a_key_the_app_made_stays_unsaved_until_someone_confirms_a_copy(
    store: BackupStore,
) -> None:
    own = store.add_target(_target("Own password file"), T0)
    assert own.key_saved_at == T0, "a password file the owner wrote is theirs to keep"
    made = store.add_target(_target("Guided", key_saved=False), T0)
    assert made.key_saved_at is None
    store.mark_key_saved(made.id, T0 + timedelta(minutes=5))
    found = store.get_target(made.id)
    assert found is not None and found.key_saved_at == T0 + timedelta(minutes=5)
    store.mark_key_saved(999, T0)  # an unknown target is nothing to mark


def test_the_proton_copy_folder_is_kept_per_target_and_mirror_runs_are_recorded(
    store: BackupStore,
) -> None:
    target = store.add_target(_target(), T0)
    assert target.mirror_path is None
    store.set_target_mirror(target.id, "/my-files/Backups")
    found = store.get_target(target.id)
    assert found is not None and found.mirror_path == "/my-files/Backups"
    run_id = store.start_run(target.id, RunKind.MIRROR, T0)
    store.finish_run(run_id, T0, RunOutcome(BackupRunStatus.SUCCEEDED, details="1 new file sent"))
    last = store.last_run(target.id, RunKind.MIRROR, succeeded_only=True)
    assert last is not None and last.details == "1 new file sent"
    store.set_target_mirror(target.id, None)
    cleared = store.get_target(target.id)
    assert cleared is not None and cleared.mirror_path is None


def test_library_bytes_is_the_size_of_every_original(store: BackupStore) -> None:
    assert store.library_bytes() == 1001 + 1002 + 1003


def test_target_settings_can_be_changed(store: BackupStore) -> None:
    created = store.add_target(_target(), T0)
    store.set_target_settings(
        created.id, TargetSettings("hourly", "22:00-06:00", Retention(0, 0, 3))
    )
    changed = store.get_target(created.id)
    assert changed is not None
    assert (changed.schedule, changed.quiet_window) == ("hourly", "22:00-06:00")
    assert changed.retention == Retention(0, 0, 3)
    assert (changed.label, changed.enabled, changed.created_at) == ("Disk", True, T0)
    store.set_target_settings(created.id, TargetSettings("manual", None, Retention()))
    again = store.get_target(created.id)
    assert again is not None and again.quiet_window is None and again.schedule == "manual"


def test_run_lifecycle(store: BackupStore) -> None:
    target = store.add_target(_target(), T0)
    first = store.start_run(target.id, RunKind.BACKUP, T0)
    running = store.get_run(first)
    assert running is not None and running.status is BackupRunStatus.RUNNING
    outcome = RunOutcome(BackupRunStatus.SUCCEEDED, "abc", 10, 2, 1, 1000, None, "fine")
    store.finish_run(first, T0 + timedelta(minutes=5), outcome)
    done = store.get_run(first)
    assert done is not None
    assert (done.status, done.snapshot_id, done.bytes_added, done.files_new) == (
        BackupRunStatus.SUCCEEDED,
        "abc",
        10,
        2,
    )
    assert (done.files_changed, done.repo_bytes, done.details) == (1, 1000, "fine")
    assert done.finished_at == T0 + timedelta(minutes=5)

    second = store.start_run(target.id, RunKind.BACKUP, T0 + timedelta(hours=1))
    store.finish_run(second, T0, RunOutcome(BackupRunStatus.FAILED, error="disk full"))
    check = store.start_run(target.id, RunKind.CHECK, T0 + timedelta(hours=2))

    assert [r.id for r in store.list_runs(target.id)] == [check, second, first]
    assert [r.id for r in store.list_runs(target.id, limit=1)] == [check]
    last = store.last_run(target.id, RunKind.BACKUP)
    assert last is not None and last.id == second and last.error == "disk full"
    good = store.last_run(target.id, RunKind.BACKUP, succeeded_only=True)
    assert good is not None and good.id == first
    assert store.last_run(target.id, RunKind.RESTORE_TEST) is None
    assert store.get_run(999) is None

    assert store.recover_interrupted_runs(T0) == 1
    recovered = store.get_run(check)
    assert recovered is not None and recovered.status is BackupRunStatus.FAILED


def test_sample_only_has_assets_older_than_the_snapshot(store: BackupStore) -> None:
    sample = store.sample_assets(10, T0)
    assert sorted(a.content_hash for a in sample) == [f"{1:064x}", f"{2:064x}"]
    assert len(store.sample_assets(1, T0)) == 1
    assert all(a.library_path.startswith("originals/") for a in sample)


# --- snapshots ------------------------------------------------------------------------------


@pytest.fixture
def live_db(tmp_path: Path) -> Iterator[tuple[Path, sqlite3.Connection]]:
    path = tmp_path / "data" / "library.db"
    path.parent.mkdir()
    conn = open_database(path)
    yield path, conn
    conn.close()


def test_snapshot_of_a_live_database_is_consistent_and_self_contained(
    live_db: tuple[Path, sqlite3.Connection], tmp_path: Path
) -> None:
    path, conn = live_db
    repo = SqliteRepository(conn)
    for n in range(50):
        repo.add_asset(new_asset(n), T0)
    assert Path(f"{path}-wal").exists(), "writes are still in the WAL"
    destination = tmp_path / "data" / "db-snapshot" / "library.db"
    SqliteSnapshotter(path).snapshot(destination)
    assert sorted(p.name for p in destination.parent.iterdir()) == ["library.db"]
    copy = open_read_only(destination)
    assert copy.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 50
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    copy.close()
    SqliteSnapshotter(path).snapshot(destination)  # replacing an older snapshot is fine


def test_snapshot_failures(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SqliteSnapshotter(tmp_path / "missing.db").snapshot(tmp_path / "out" / "library.db")
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"this is not a database" * 100)
    with pytest.raises(BackupError, match="snapshot"):
        SqliteSnapshotter(garbage).snapshot(tmp_path / "out" / "library.db")
    assert list((tmp_path / "out").iterdir()) == [], "no half-written snapshot left behind"
