"""BackupService with fakes: FEATURES 9b.1-9b.8 behaviour, independent of restic."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import Blake3Hasher
from photo_assistant.app.backup import (
    BACKUP_JOB,
    MIRROR_JOB,
    RESTORE_TEST_JOB,
    BackupConfig,
    BackupService,
    UnknownTargetError,
)
from photo_assistant.domain.backup import (
    BACKUP_FOLDERS,
    BackupRunStatus,
    NewBackupTarget,
    PlaceFacts,
    Retention,
    RunKind,
    TargetSettings,
)
from photo_assistant.domain.schedule import InvalidScheduleError
from photo_assistant.ports.backup import (
    AssetFile,
    BackupError,
    Disk,
    MirrorSignInError,
    WrongPasswordError,
)
from tests.fakes_backup import (
    FakeEngine,
    FakeMirror,
    FakePlaces,
    FakeQueue,
    FakeSnapshotter,
    FakeVault,
    InMemoryBackupStore,
    SteppingClock,
)

T0 = datetime(2026, 9, 29, 1, 0, tzinfo=UTC)


class World:
    def __init__(self, tmp_path: Path, **config: object) -> None:
        self.root = tmp_path / "data"
        self.root.mkdir()
        self.password = tmp_path / "secrets" / "restic-password"
        self.password.parent.mkdir()
        self.password.write_text("correct horse\n")
        self.assets = self._make_assets()
        self.store = InMemoryBackupStore([(a, T0 - timedelta(days=1)) for a in self.assets])
        self.engine = FakeEngine()
        self.snapshotter = FakeSnapshotter()
        self.clock = SteppingClock(T0)
        self.queue = FakeQueue()
        self.places = FakePlaces()
        self.vault = FakeVault(tmp_path / "keys")
        self.mirror = FakeMirror()
        self.disk = tmp_path / "usb"
        self.disk.mkdir()
        self.service = BackupService(
            self.store,
            self.engine,
            self.snapshotter,
            Blake3Hasher(),
            self.clock,
            BackupConfig(**{"data_root": self.root, "local_tz": UTC, **config}),  # type: ignore[arg-type]
            queue=self.queue,
            places=self.places,
            vault=self.vault,
            mirror=self.mirror,
        )

    def _make_assets(self) -> list[AssetFile]:
        hasher = Blake3Hasher()
        assets = []
        for n in range(3):
            relative = f"originals/2020/01/photo{n}.jpg"
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"photo {n}".encode())
            assets.append(AssetFile(n + 1, hasher.hash_file(path), relative))
        return assets

    def target(self, **overrides: object) -> int:
        values: dict[str, object] = {
            "label": "External disk",
            "repository": str(self.root.parent / "backup-disk" / "photos"),
            "password_file": str(self.password),
            "schedule": "daily 02:30",
        }
        values.update(overrides)
        return self.service.add_target(NewBackupTarget(**values)).id  # type: ignore[arg-type]


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_backup_snapshots_the_database_first_then_runs_and_prunes(world: World) -> None:
    target_id = world.target(retention=Retention(daily=3, weekly=2, monthly=1))
    run = world.service.run_now(target_id)
    assert run.status is BackupRunStatus.SUCCEEDED
    assert run.kind is RunKind.BACKUP
    assert world.snapshotter.taken == [world.root / "db-snapshot" / "library.db"]
    assert world.engine.calls == ["ensure", "backup", "forget", "size"]
    assert world.engine.backed_up == [(world.root, BACKUP_FOLDERS)]
    assert world.engine.retention == Retention(3, 2, 1)
    assert (run.snapshot_id, run.bytes_added, run.files_new, run.repo_bytes) == (
        f"{1:064x}",
        1234,
        3,
        99_000,
    )
    assert run.finished_at is not None and run.error is None


def test_backup_never_includes_rebuildable_thumbnails() -> None:
    assert "derived" not in BACKUP_FOLDERS
    assert {"originals", "recipes", "config", "db-snapshot"} <= set(BACKUP_FOLDERS)


def test_a_failing_backup_is_recorded_with_its_reason_and_nothing_is_pruned(
    world: World,
) -> None:
    world.engine.fail["backup"] = WrongPasswordError("wrong password for the backup")
    run = world.service.run_now(world.target())
    assert run.status is BackupRunStatus.FAILED
    assert run.error == "wrong password for the backup"
    assert "forget" not in world.engine.calls


def test_a_failed_database_snapshot_stops_the_run_before_restic(world: World) -> None:
    world.snapshotter.fail = BackupError("could not snapshot the library database: disk I/O")
    run = world.service.run_now(world.target())
    assert run.status is BackupRunStatus.FAILED and "snapshot" in (run.error or "")
    assert "backup" not in world.engine.calls


def test_an_os_error_is_recorded_as_a_failed_run(world: World) -> None:
    world.engine.fail["ensure"] = PermissionError("permission denied: /media/c")
    run = world.service.run_now(world.target())
    assert run.status is BackupRunStatus.FAILED and "permission denied" in (run.error or "")


def test_an_unexpected_error_is_recorded_then_raised(world: World) -> None:
    world.engine.fail["backup"] = KeyError("surprise")
    target_id = world.target()
    with pytest.raises(KeyError):
        world.service.run_now(target_id)
    (run,) = world.service.runs(target_id)
    assert run.status is BackupRunStatus.FAILED and "KeyError" in (run.error or "")


def test_targets_are_validated(world: World, tmp_path: Path) -> None:
    inside = world.root / "restic-password"
    inside.write_text("x")
    with pytest.raises(ValueError, match="outside the library"):
        world.target(password_file=str(inside))
    with pytest.raises(ValueError, match="absolute"):
        world.target(password_file="restic-password")
    with pytest.raises(ValueError, match="not found"):
        world.target(password_file=str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="inside the library"):
        world.target(repository=str(world.root / "backup"))
    with pytest.raises(ValueError, match="inside the library"):
        world.target(repository=str(tmp_path))
    with pytest.raises(ValueError, match="absolute"):
        world.target(repository="backup")
    with pytest.raises(ValueError, match="schedule"):
        world.target(schedule="every now and then")
    rclone = world.target(label="Server", repository="rclone:server:photos")
    assert world.service.target(rclone).kind.value == "rclone"
    world.target(label="Disk")
    with pytest.raises(ValueError, match="already exists"):
        world.target(label="Disk")
    assert [t.label for t in world.service.targets()] == ["Server", "Disk"]


def test_a_backup_repository_may_not_overlap_a_source_folder(tmp_path: Path) -> None:
    """QA A5: restic would write its repository into a folder the library only reads."""
    pictures = tmp_path / "media" / "Pictures"
    pictures.mkdir(parents=True)
    world = World(tmp_path, source_roots=lambda: [pictures])
    with pytest.raises(ValueError, match="source folder"):
        world.target(repository=str(pictures / "backup"))
    with pytest.raises(ValueError, match="source folder"):
        world.target(label="around", repository=str(tmp_path / "media"))
    world.target(repository=str(tmp_path / "disk" / "photos"))
    assert world.service.repository_overlaps(tmp_path / "disk")
    assert world.service.repository_overlaps(tmp_path / "disk" / "photos" / "data")
    assert not world.service.repository_overlaps(pictures)


def test_scheduled_runs_happen_once_per_slot(world: World) -> None:
    target_id = world.target(schedule="daily 02:30")
    world.target(label="Only by hand", schedule="manual")
    world.clock.current = T0.replace(hour=2, minute=29)
    assert world.service.run_due() == []
    world.clock.current = T0.replace(hour=2, minute=31)
    (run,) = world.service.run_due()
    assert run.target_id == target_id
    world.clock.current = T0.replace(hour=3, minute=0)
    assert world.service.run_due() == [], "already ran for this slot"
    world.clock.current = T0 + timedelta(days=5)
    assert len(world.service.run_due()) == 1, "after days off: one catch-up run, not five"


def test_disabled_targets_and_quiet_windows_are_respected(world: World) -> None:
    hourly = world.target(schedule="hourly", quiet_window="22:00-06:00")
    daily = world.target(label="Disk 2", schedule="daily 02:30")
    world.service.set_enabled(daily, enabled=False)
    world.clock.current = T0.replace(hour=12)
    assert world.service.run_due() == [], "hourly waits for the quiet window"
    world.clock.current = T0.replace(hour=22, minute=5)
    assert [r.target_id for r in world.service.run_due()] == [hourly]
    with pytest.raises(UnknownTargetError):
        world.service.set_enabled(999, enabled=True)


def test_changed_settings_move_the_next_run(world: World) -> None:
    target_id = world.target(schedule="daily 02:30")
    changed = world.service.change_settings(
        target_id, TargetSettings("weekly sun 03:00", "01:00-05:00", Retention(3, 0, 0))
    )
    assert changed.schedule == "weekly sun 03:00" and changed.retention == Retention(3, 0, 0)
    (status,) = world.service.status()
    assert status.next_run_at == datetime(2026, 10, 4, 3, 0, tzinfo=UTC)
    with pytest.raises(UnknownTargetError):
        world.service.change_settings(999, TargetSettings("manual", None, Retention()))


def test_status_shows_next_run_size_and_overdue(world: World) -> None:
    target_id = world.target(schedule="daily 02:30")
    (fresh,) = world.service.status()
    assert fresh.last_success_at is None and fresh.last_run is None
    assert fresh.next_run_at == T0.replace(hour=2, minute=30)
    assert not fresh.overdue and not fresh.needs_attention

    world.clock.current = T0.replace(hour=2, minute=30)
    world.service.run_now(target_id)
    (ok,) = world.service.status()
    assert ok.last_success_at == T0.replace(hour=2, minute=30)
    assert ok.repo_bytes == 99_000
    assert ok.next_run_at == T0.replace(hour=2, minute=30) + timedelta(days=1)

    world.engine.fail["backup"] = BackupError("disk full")
    world.clock.current = T0 + timedelta(days=3)
    world.service.run_now(target_id)
    (late,) = world.service.status()
    assert late.overdue and late.failing and late.needs_attention
    assert late.repo_bytes == 99_000, "size of the last good snapshot"
    assert late.last_run is not None and late.last_run.error == "disk full"


def test_disabled_targets_have_no_next_run_and_raise_no_banner(world: World) -> None:
    target_id = world.target()
    world.service.set_enabled(target_id, enabled=False)
    world.clock.current = T0 + timedelta(days=30)
    (status,) = world.service.status()
    assert status.next_run_at is None and status.overdue and not status.needs_attention


def test_status_in_the_machine_zone_by_default(tmp_path: Path) -> None:
    world = World(tmp_path, local_tz=None)
    world.target()
    (status,) = world.service.status()
    assert status.next_run_at is not None and status.next_run_at.tzinfo is not None


def test_restore_test_verifies_hashes_of_a_sample(world: World) -> None:
    target_id = world.target()
    world.service.run_now(target_id)
    run = world.service.restore_test(target_id)
    assert run.kind is RunKind.RESTORE_TEST
    assert run.status is BackupRunStatus.SUCCEEDED, run.error
    assert "restored 4" in (run.details or "") and "every hash matches" in (run.details or "")
    assert run.snapshot_id == f"{1:064x}"


def test_restore_test_reports_corrupt_and_missing_files(world: World) -> None:
    target_id = world.target()
    world.service.run_now(target_id)
    world.engine.corrupt.add(world.assets[0].library_path)
    (world.root / world.assets[1].library_path).unlink()  # simulate: not in the backup
    run = world.service.restore_test(target_id, sample_size=3)
    assert run.status is BackupRunStatus.FAILED
    assert "2 failed" in (run.error or "")
    assert "do not match the hash" in (run.error or "")
    assert "missing from the backup" in (run.error or "")


def test_restore_test_flags_a_missing_database_snapshot(world: World) -> None:
    target_id = world.target()
    world.service.run_now(target_id)
    (world.root / "db-snapshot" / "library.db").unlink()
    run = world.service.restore_test(target_id, sample_size=0)
    assert run.status is BackupRunStatus.FAILED
    assert "database snapshot missing" in (run.error or "")


def test_restore_test_without_any_snapshot_fails_clearly(world: World) -> None:
    run = world.service.restore_test(world.target())
    assert run.status is BackupRunStatus.FAILED
    assert run.error == "no snapshot to restore from yet"


def test_restore_scratch_folder_must_be_outside_the_library(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside the library"):
        World(tmp_path, scratch_dir=tmp_path / "data" / "tmp")


def test_restore_test_uses_the_configured_scratch_folder(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    world = World(tmp_path, scratch_dir=scratch)
    target_id = world.target()
    world.service.run_now(target_id)
    assert world.service.restore_test(target_id).status is BackupRunStatus.SUCCEEDED
    assert list(scratch.iterdir()) == [], "cleaned up"


def test_check_is_recorded(world: World) -> None:
    target_id = world.target()
    run = world.service.check(target_id, read_data_subset="5%")
    assert run.status is BackupRunStatus.SUCCEEDED and run.kind is RunKind.CHECK
    assert world.engine.calls == ["check 5%"]
    assert "read 5%" in (run.details or "")
    assert world.service.check(target_id).details == "repository is healthy"


def test_manual_runs_go_through_the_job_queue(world: World) -> None:
    target_id = world.target()
    assert world.service.queue_run(target_id) == 1
    assert world.service.queue_restore_test(target_id) == 2
    assert world.queue.jobs == [
        (BACKUP_JOB, {"target_id": target_id}),
        (RESTORE_TEST_JOB, {"target_id": target_id}),
    ]
    handlers = world.service.job_handlers()
    handlers[BACKUP_JOB]({"target_id": target_id})
    handlers[RESTORE_TEST_JOB]({"target_id": target_id})
    kinds = [r.kind for r in world.service.runs(target_id)]
    # the first successful backup is proven by a restore test of its own (issue 3)
    assert kinds == [RunKind.RESTORE_TEST, RunKind.RESTORE_TEST, RunKind.BACKUP]
    with pytest.raises(UnknownTargetError):
        world.service.queue_run(999)


def test_queueing_needs_a_queue(tmp_path: Path) -> None:
    world = World(tmp_path)
    service = BackupService(
        world.store,
        world.engine,
        world.snapshotter,
        Blake3Hasher(),
        world.clock,
        BackupConfig(data_root=world.root),
    )
    target_id = world.target()
    with pytest.raises(RuntimeError, match="job queue"):
        service.queue_run(target_id)


def test_interrupted_runs_are_marked_failed_at_startup(world: World) -> None:
    target_id = world.target()
    world.store.start_run(target_id, RunKind.BACKUP, T0)
    assert world.service.recover_interrupted() == 1
    (run,) = world.service.runs(target_id)
    assert run.status is BackupRunStatus.FAILED


# --- guided setup (issue 3): where, does it fit, the key, the first run ------------------------

GB = 1000**3


def test_setup_puts_the_backup_in_its_own_folder_makes_a_key_and_queues_the_first_run(
    world: World,
) -> None:
    target, key = world.service.set_up("USB disk", str(world.disk))
    assert target.repository == str(world.disk / "photo-assistant-backup")
    assert (target.schedule, target.retention) == ("daily 02:30", Retention(7, 4, 12))
    assert Path(target.password_file).read_text().strip() == key == "secret-1"
    assert target.key_saved_at is None, "nobody confirmed a copy of the key yet"
    assert world.queue.jobs == [(BACKUP_JOB, {"target_id": target.id})]


@pytest.mark.parametrize(
    ("place", "repository"),
    [
        ("rclone:proton:", "rclone:proton:photo-assistant-backup"),
        ("rclone:nas:family/", "rclone:nas:family/photo-assistant-backup"),
        ("rclone:nas:family", "rclone:nas:family/photo-assistant-backup"),
    ],
)
def test_setup_on_a_cloud_remote_uses_a_folder_of_that_remote(
    world: World, place: str, repository: str
) -> None:
    target, _ = world.service.set_up("Cloud", place)
    assert target.repository == repository
    assert world.places.asked == [repository]


def test_the_plan_reports_library_size_free_space_and_refuses_what_does_not_fit(
    world: World,
) -> None:
    world.store.asset_bytes = 40 * GB
    repository = str(world.disk / "photo-assistant-backup")
    world.places.by_repository[repository] = PlaceFacts(free_bytes=25 * GB)
    found, plan = world.service.plan(str(world.disk))
    assert found == repository and not plan.ok
    assert (plan.library_bytes, plan.free_bytes) == (40 * GB, 25 * GB)
    with pytest.raises(ValueError, match=r"15\.0 GB missing"):
        world.service.set_up("USB disk", str(world.disk))
    assert world.store.list_targets() == [] and world.queue.jobs == []
    assert list(world.vault.folder.glob("*")) == [], "no key is made for a refused setup"


@pytest.mark.parametrize("place", ["relative/folder", "", "  ", "rclone:", "rclone:no-colon"])
def test_a_place_that_is_not_a_full_path_or_a_remote_is_refused(world: World, place: str) -> None:
    _, plan = world.service.plan(place)
    assert not plan.ok
    assert world.places.asked == [], "the machine is not even asked"


def test_a_backup_inside_the_library_or_a_source_folder_is_refused(tmp_path: Path) -> None:
    pictures = tmp_path / "Pictures"
    pictures.mkdir()
    world = World(tmp_path, source_roots=lambda: [pictures])
    for place in (world.root, world.root / "originals", pictures, pictures / "2019"):
        _, plan = world.service.plan(str(place))
        assert plan.problem is not None and "cannot live inside" in plan.problem, place


def test_a_second_setup_with_the_same_name_is_refused_and_leaves_no_key_behind(
    world: World,
) -> None:
    world.service.set_up("USB disk", str(world.disk))
    with pytest.raises(ValueError, match="already exists"):
        world.service.set_up("usb DISK ", str(world.disk / "other"))
    assert len(list(world.vault.folder.glob("*"))) == 1


def test_setup_validates_the_schedule_before_making_a_key(world: World) -> None:
    with pytest.raises(InvalidScheduleError):
        world.service.set_up("USB disk", str(world.disk), schedule="often")
    assert not world.vault.folder.exists()


def test_the_recovery_sheet_gives_the_key_until_and_after_it_is_confirmed_saved(
    world: World,
) -> None:
    target, key = world.service.set_up("USB disk", str(world.disk))
    sheet = world.service.recovery(target.id)
    assert (sheet.label, sheet.repository, sheet.key) == ("USB disk", target.repository, key)
    assert world.service.status()[0].needs_attention, "an unsaved key is flagged"
    world.clock.current += timedelta(minutes=5)
    world.service.confirm_key_saved(target.id)
    assert world.service.target(target.id).key_saved_at == world.clock.current
    world.service.confirm_key_saved(target.id)
    assert world.service.target(target.id).key_saved_at == world.clock.current
    assert world.service.recovery(target.id).key == key
    with pytest.raises(UnknownTargetError):
        world.service.recovery(999)
    with pytest.raises(UnknownTargetError):
        world.service.confirm_key_saved(999)


def test_a_missing_key_file_is_reported_not_crashed_on(world: World) -> None:
    target, _ = world.service.set_up("USB disk", str(world.disk))
    Path(target.password_file).unlink()
    with pytest.raises(BackupError, match="key file is gone"):
        world.service.recovery(target.id)


def test_places_lists_plugged_in_disks_and_cloud_remotes(world: World) -> None:
    world.places.found_disks = [Disk("/media/c/USB", "USB", 64 * GB)]
    world.places.found_remotes = ["proton", "nas"]
    assert world.service.places() == ([Disk("/media/c/USB", "USB", 64 * GB)], ["proton", "nas"])


# --- the recovery guarantee: restore tests run by themselves -----------------------------------


def _work(world: World) -> None:
    """What the worker does with the queued jobs."""
    handlers = world.service.job_handlers()
    jobs, world.queue.jobs = world.queue.jobs, []
    for kind, payload in jobs:
        handlers[kind](payload)


def test_the_first_backup_is_proven_by_a_restore_test_straight_away(world: World) -> None:
    target, _ = world.service.set_up("USB disk", str(world.disk))
    _work(world)
    kinds = [(r.kind, r.status) for r in world.service.runs(target.id)]
    assert kinds == [
        (RunKind.RESTORE_TEST, BackupRunStatus.SUCCEEDED),
        (RunKind.BACKUP, BackupRunStatus.SUCCEEDED),
    ]
    status = world.service.status()[0]
    assert status.last_proven_at == world.clock.current and not status.restore_failing


def test_a_failed_first_backup_is_not_followed_by_a_restore_test(world: World) -> None:
    world.engine.fail["backup"] = BackupError("disk unplugged")
    target, _ = world.service.set_up("USB disk", str(world.disk))
    _work(world)
    assert [r.kind for r in world.service.runs(target.id)] == [RunKind.BACKUP]


def test_due_checks_prove_each_backup_again_every_week(world: World) -> None:
    target, _ = world.service.set_up("USB disk", str(world.disk), schedule="manual")
    _work(world)
    world.clock.current += timedelta(days=6)
    world.service.run_due()
    assert len(world.service.runs(target.id)) == 2, "not yet"
    world.clock.current += timedelta(days=1)
    world.service.run_due()
    world.service.run_due()
    tests = [r for r in world.service.runs(target.id) if r.kind is RunKind.RESTORE_TEST]
    assert len(tests) == 2, "once, not on every check"


def test_a_failing_restore_test_raises_the_banner_and_is_retried_the_next_day(
    world: World,
) -> None:
    target, _ = world.service.set_up("USB disk", str(world.disk), schedule="manual")
    world.service.confirm_key_saved(target.id)
    world.engine.corrupt.add(world.assets[0].library_path)
    _work(world)
    status = world.service.status()[0]
    assert status.restore_failing and status.needs_attention and status.last_proven_at is None
    world.engine.corrupt.clear()
    world.service.run_due()
    assert world.service.status()[0].restore_failing, "not retried within the day"
    world.clock.current += timedelta(days=1)
    world.service.run_due()
    status = world.service.status()[0]
    assert not status.restore_failing and not status.needs_attention
    assert status.last_proven_at == world.clock.current


def test_a_disabled_target_is_not_restore_tested(world: World) -> None:
    target, _ = world.service.set_up("USB disk", str(world.disk), schedule="manual")
    _work(world)
    world.service.set_enabled(target.id, False)
    world.clock.current += timedelta(days=30)
    world.service.run_due()
    assert len(world.service.runs(target.id)) == 2


# --- an off-site copy on Proton Drive (issue 14) -----------------------------------------------

PROTON = "/my-files/Backups"


def mirrored(world: World) -> int:
    target_id = world.target()
    world.service.set_mirror(target_id, PROTON)
    return target_id


def kinds(world: World, target_id: int) -> list[tuple[RunKind, BackupRunStatus]]:
    return [(r.kind, r.status) for r in reversed(world.service.runs(target_id))]


def test_after_a_successful_backup_the_copy_on_proton_is_brought_up_to_date(world: World) -> None:
    target_id = mirrored(world)
    world.service.run_now(target_id)
    repository = Path(world.service.target(target_id).repository)
    assert world.mirror.calls == [(repository, PROTON, world.root / "mirror" / f"{target_id}.json")]
    assert kinds(world, target_id) == [
        (RunKind.BACKUP, BackupRunStatus.SUCCEEDED),
        (RunKind.MIRROR, BackupRunStatus.SUCCEEDED),
    ]
    copy = world.service.runs(target_id)[0]
    assert copy.details == "2 new files sent (5 MB), 1 old file removed"
    (status,) = world.service.status()
    assert status.last_mirror_at == copy.finished_at and not status.mirror_failing
    assert not status.needs_attention


def test_without_a_copy_configured_or_after_a_failed_backup_nothing_is_sent(world: World) -> None:
    plain = world.target()
    world.service.run_now(plain)
    world.service.set_mirror(plain, PROTON)
    world.queue.jobs.clear()
    world.engine.fail["backup"] = BackupError("disk unplugged")
    world.service.run_now(plain)
    assert world.mirror.calls == []
    assert RunKind.MIRROR not in [k for k, _ in kinds(world, plain)]


def test_a_failed_copy_is_recorded_and_raises_the_banner_until_it_works_again(
    world: World,
) -> None:
    target_id = mirrored(world)
    world.service.confirm_key_saved(target_id)
    world.mirror.fail = MirrorSignInError("Proton Drive is not signed in: run 'x'")
    backup = world.service.run_now(target_id)
    assert backup.status is BackupRunStatus.SUCCEEDED, "the backup itself is fine"
    (status,) = world.service.status()
    assert status.mirror_failing and status.needs_attention
    assert status.mirror_error == "Proton Drive is not signed in: run 'x'"
    assert status.last_mirror_at is None
    world.mirror.fail = None
    world.service.run_now(target_id)
    (status,) = world.service.status()
    assert not status.mirror_failing and status.mirror_error is None
    assert status.last_mirror_at is not None


def test_scheduled_backups_are_copied_too(world: World) -> None:
    target_id = mirrored(world)
    world.clock.current = T0 + timedelta(hours=2)  # past 02:30
    world.service.run_due()
    assert (RunKind.MIRROR, BackupRunStatus.SUCCEEDED) in kinds(world, target_id)


def test_switching_the_copy_on_queues_a_first_copy_when_a_backup_exists(world: World) -> None:
    target_id = world.target()
    world.service.set_mirror(target_id, PROTON)
    assert world.queue.jobs == [], "nothing to copy before the first backup"
    world.service.run_now(target_id)
    world.service.set_mirror(target_id, None)
    assert world.service.target(target_id).mirror_path is None
    world.service.set_mirror(target_id, "/my-files/Elsewhere")
    assert world.queue.jobs == [(MIRROR_JOB, {"target_id": target_id})]
    world.service.job_handlers()[MIRROR_JOB]({"target_id": target_id})
    assert world.mirror.calls[-1][1] == "/my-files/Elsewhere"


def test_a_copy_job_for_a_target_whose_copy_was_switched_off_does_nothing(world: World) -> None:
    target_id = mirrored(world)
    world.service.set_mirror(target_id, None)
    world.service.job_handlers()[MIRROR_JOB]({"target_id": target_id})
    assert world.mirror.calls == []


@pytest.mark.parametrize("path", ["/photos", "/trash", "my-files", "/my-files/../x", ""])
def test_the_copy_must_go_in_a_folder_in_my_files(world: World, path: str) -> None:
    with pytest.raises(ValueError, match="My files"):
        world.service.set_mirror(world.target(), path)


def test_only_a_backup_on_this_machine_can_have_a_copy(world: World) -> None:
    cloud = world.target(repository="rclone:nas:photos")
    with pytest.raises(ValueError, match="folder or disk"):
        world.service.set_mirror(cloud, PROTON)
    with pytest.raises(UnknownTargetError):
        world.service.set_mirror(999, PROTON)


def test_without_proton_set_up_on_the_server_the_copy_cannot_be_switched_on(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.service._mirror = None
    with pytest.raises(ValueError, match="not available"):
        world.service.set_mirror(world.target(), PROTON)
