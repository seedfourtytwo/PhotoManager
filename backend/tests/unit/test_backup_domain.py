"""Backup value types: retention, target validation, restore-test summaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from photo_assistant.domain.backup import (
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    PlaceFacts,
    RestoreCheck,
    RestoreTestReport,
    Retention,
    RunKind,
    TargetKind,
    TargetSettings,
    TargetStatus,
    plan_backup,
    restore_proof_due,
    size_text,
    target_kind,
)
from photo_assistant.domain.schedule import InvalidScheduleError


def test_default_retention_is_seven_daily_four_weekly_twelve_monthly() -> None:
    assert Retention().as_dict() == {"daily": 7, "weekly": 4, "monthly": 12}


@pytest.mark.parametrize("counts", [(0, 0, 0), (-1, 4, 12)])
def test_retention_must_keep_something(counts: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError, match="retention"):
        Retention(*counts)


def test_target_kind_follows_the_repository() -> None:
    assert target_kind("/media/c/Backup/photos") is TargetKind.LOCAL
    assert target_kind("rclone:server:photos") is TargetKind.RCLONE


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"label": " "}, ValueError),
        ({"repository": ""}, ValueError),
        ({"schedule": "often"}, InvalidScheduleError),
        ({"quiet_window": "night"}, InvalidScheduleError),
    ],
)
def test_new_targets_are_validated(overrides: dict[str, str], error: type[Exception]) -> None:
    values: dict[str, Any] = {"label": "Disk", "repository": "/r", "password_file": "/p"}
    values |= overrides
    with pytest.raises(error):
        NewBackupTarget(**values)


def test_restore_report_summary_lists_at_most_five_failures() -> None:
    bad = tuple(RestoreCheck(f"originals/{n}.jpg", False, "missing") for n in range(7))
    report = RestoreTestReport("a" * 64, (RestoreCheck("db", True), *bad))
    assert not report.ok
    summary = report.summary()
    assert "restored 8 photos from aaaaaaaa; 7 failed" in summary
    assert summary.count("missing") == 5
    assert RestoreTestReport("b" * 64, ()).ok
    assert not RestoreTestReport(None, ()).ok


def test_settings_are_validated_with_the_schedule_language() -> None:
    settings = TargetSettings("weekly sun 03:00", "22:00-06:00", Retention(1, 0, 0))
    assert settings.schedule == "weekly sun 03:00"
    with pytest.raises(InvalidScheduleError, match="schedule"):
        TargetSettings("now and then", None, Retention())
    with pytest.raises(InvalidScheduleError, match="quiet window"):
        TargetSettings("hourly", "22:00", Retention())


# --- planning a new backup: does the library fit, and is the place sound? (issue 3) -----------

GB = 1000**3


def test_a_roomy_empty_place_on_another_disk_is_fine() -> None:
    plan = plan_backup(40 * GB, PlaceFacts(free_bytes=200 * GB))
    assert plan.ok and plan.problem is None and plan.warnings == ()
    assert (plan.library_bytes, plan.free_bytes) == (40 * GB, 200 * GB)


def test_a_place_too_small_is_refused_and_says_how_much_is_missing() -> None:
    plan = plan_backup(40 * GB, PlaceFacts(free_bytes=25 * GB))
    assert not plan.ok
    assert plan.problem == (
        "not enough room: the library is 40.0 GB and only 25.0 GB is free there (15.0 GB missing)"
    )


@pytest.mark.parametrize(
    ("free", "tight"),
    [(40 * GB, True), (48 * GB - 1, True), (48 * GB, False)],
    ids=["exactly fits", "just under 20 % headroom", "20 % headroom"],
)
def test_under_twenty_percent_headroom_fits_with_a_warning(free: int, tight: bool) -> None:
    plan = plan_backup(40 * GB, PlaceFacts(free_bytes=free))
    assert plan.ok
    assert any("little room to grow" in w for w in plan.warnings) is tight


def test_an_empty_library_fits_anywhere_without_a_headroom_warning() -> None:
    assert plan_backup(0, PlaceFacts(free_bytes=0)).warnings == ()


def test_unknown_free_space_is_allowed_but_said() -> None:
    plan = plan_backup(40 * GB, PlaceFacts(free_bytes=None))
    assert plan.ok and plan.warnings == ("free space there can't be checked",)


def test_the_same_disk_as_the_library_is_allowed_with_a_warning() -> None:
    plan = plan_backup(GB, PlaceFacts(free_bytes=100 * GB, same_disk=True))
    assert plan.ok and "same disk as the library" in plan.warnings[0]


def test_a_place_we_cannot_write_to_or_that_holds_a_backup_is_refused_before_space() -> None:
    locked = plan_backup(GB, PlaceFacts(free_bytes=0, write_error="Permission denied"))
    assert locked.problem == "can't write there: Permission denied"
    taken = plan_backup(GB, PlaceFacts(free_bytes=0, holds_backup=True))
    assert taken.problem is not None and "already a backup" in taken.problem


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (0, "0 MB"),
        (4_400_000, "4 MB"),
        (999_949_999, "1000 MB"),
        (GB, "1.0 GB"),
        (1536 * 10**6, "1.5 GB"),
    ],
)
def test_sizes_read_in_megabytes_then_gigabytes(size: int, text: str) -> None:
    assert size_text(size) == text


# --- proving a backup can be restored (issue 3) -----------------------------------------------

NOON = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _test_run(status: BackupRunStatus, started: datetime) -> BackupRun:
    return BackupRun(1, 1, RunKind.RESTORE_TEST, status, started)


def test_no_restore_proof_is_due_before_the_first_successful_backup() -> None:
    assert not restore_proof_due(None, None, NOON)


def test_the_first_successful_backup_is_proven_at_once() -> None:
    assert restore_proof_due(NOON, None, NOON)


def test_a_proven_backup_is_proven_again_after_a_week() -> None:
    ok = _test_run(BackupRunStatus.SUCCEEDED, NOON)
    assert not restore_proof_due(NOON, ok, NOON + timedelta(days=7, seconds=-1))
    assert restore_proof_due(NOON, ok, NOON + timedelta(days=7))


def test_a_failed_restore_test_is_retried_after_a_day_not_every_minute() -> None:
    bad = _test_run(BackupRunStatus.FAILED, NOON)
    assert not restore_proof_due(NOON, bad, NOON + timedelta(hours=23))
    assert restore_proof_due(NOON, bad, NOON + timedelta(days=1))


def test_a_restore_test_still_running_is_not_started_twice() -> None:
    running = _test_run(BackupRunStatus.RUNNING, NOON - timedelta(days=30))
    assert not restore_proof_due(NOON, running, NOON)


def test_a_failing_restore_test_or_an_unsaved_key_needs_attention() -> None:
    target = BackupTarget(1, "Disk", "/r", "/p", "manual", None, Retention(), True, NOON, NOON)
    calm = TargetStatus(target, NOON, None, None, None, False)
    assert not calm.needs_attention
    assert replace(calm, restore_failing=True).needs_attention
    unsaved = replace(calm, target=replace(target, key_saved_at=None))
    assert unsaved.needs_attention
    off = replace(unsaved, target=replace(unsaved.target, enabled=False))
    assert not off.needs_attention, "a disabled target stays quiet"
