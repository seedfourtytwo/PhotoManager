"""Backup value types: retention, target validation, restore-test summaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest

from photo_assistant.domain.backup import (
    SKIP_RETRY,
    BackupRun,
    BackupRunStatus,
    BackupTarget,
    NewBackupTarget,
    PlaceFacts,
    Problem,
    Protection,
    RestoreCheck,
    RestoreTestReport,
    Retention,
    RunKind,
    Severity,
    TargetKind,
    TargetSettings,
    TargetStatus,
    backup_due,
    plan_backup,
    probe_allowed,
    protection,
    restore_proof_due,
    size_text,
    target_kind,
)
from photo_assistant.domain.schedule import InvalidScheduleError, parse_schedule, parse_window


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


# --- skipped places and two-place protection ---------------------------------------------------

_ids = count(1)


def status(label: str = "Disk", **overrides: Any) -> TargetStatus:
    target = BackupTarget(
        next(_ids), label, "/r", "/p", "daily 02:30", None, Retention(), True, NOON, NOON
    )
    values: dict[str, Any] = {
        "target": target,
        "last_success_at": NOON,
        "last_run": None,
        "repo_bytes": None,
        "next_run_at": None,
        "overdue": False,
    }
    values |= overrides
    return TargetStatus(**values)


def _failed_run(error: str | None) -> BackupRun:
    return BackupRun(1, 1, RunKind.BACKUP, BackupRunStatus.FAILED, NOON, error=error)


def _messages(result: Protection, severity: Severity) -> list[str]:
    return [p.message for p in result.problems if p.severity is severity]


def test_two_fresh_places_are_protected_and_raise_nothing() -> None:
    result = protection([status("A"), status("B")])
    assert (result.places_ok, result.places_total) == (2, 2)
    assert result.protected
    assert result.problems == ()


def test_a_copy_on_proton_counts_as_a_second_place() -> None:
    plain = status("A")
    mirrored = replace(
        plain,
        target=replace(plain.target, mirror_path="/proton/a"),
        last_mirror_at=NOON,
    )
    result = protection([mirrored])
    assert (result.places_ok, result.places_total) == (2, 2)
    assert result.protected
    assert result.problems == ()


def test_a_disabled_target_is_not_a_place() -> None:
    off = status("Off")
    off = replace(off, target=replace(off.target, enabled=False))
    result = protection([status("A"), off])
    assert (result.places_ok, result.places_total) == (1, 1)


def test_no_places_warns_that_nothing_is_backed_up() -> None:
    result = protection([])
    assert not result.protected
    assert result.problems == (
        Problem(
            Severity.WARNING,
            "No backup is set up: the photos exist only on this computer. Add two backup places.",
        ),
    )


def test_one_place_warns_to_add_a_second() -> None:
    result = protection([status("A")])
    assert _messages(result, Severity.WARNING) == [
        "Only one backup place is set up: add a second, "
        "so one lost disk is not the end of the photos."
    ]
    assert _messages(result, Severity.ALERT) == []


def test_fewer_than_two_healthy_places_is_an_alert() -> None:
    result = protection([status("A"), status("B", last_success_at=None)])
    assert _messages(result, Severity.ALERT) == ["Only 1 of 2 backup places is up to date."]


@pytest.mark.parametrize(
    "flag",
    [
        {"last_run": _failed_run("boom")},
        {"overdue": True},
        {"restore_failing": True},
        {"mirror_error": "not signed in"},
        {"mirror_overdue": True},
        {"last_mirror_at": None},
    ],
    ids=[
        "failing",
        "overdue",
        "restore_failing",
        "mirror_failing",
        "mirror_overdue",
        "never_copied",
    ],
)
def test_each_fault_takes_one_place_out_of_a_fresh_pair(flag: dict[str, Any]) -> None:
    """One target is two places (the repository and its Proton copy): one fault, one place."""
    base = status("A")
    fresh = replace(base, target=replace(base.target, mirror_path="/proton/a"), last_mirror_at=NOON)
    result = protection([replace(fresh, **flag)])
    assert (result.places_ok, result.places_total) == (1, 2)
    assert not result.protected
    assert "Only 1 of 2 backup places is up to date." in _messages(result, Severity.ALERT)


def test_a_failed_backup_alerts_with_its_reason() -> None:
    failing = status("A", last_run=_failed_run("disk full"))
    result = protection([failing, status("B")])
    assert (
        Problem(Severity.ALERT, "A: the last backup failed: disk full", failing.target.id)
        in result.problems
    )


def test_a_failed_backup_without_a_reason_says_so() -> None:
    failing = status("A", last_run=_failed_run(None))
    result = protection([failing, status("B")])
    assert "A: the last backup failed: no reason given" in _messages(result, Severity.ALERT)


def test_a_failed_restore_test_alerts() -> None:
    result = protection([status("A", restore_failing=True), status("B")])
    assert "A: the last restore test failed. Open Backups and run it again." in _messages(
        result, Severity.ALERT
    )


def test_a_failed_proton_copy_alerts_and_is_not_also_called_out_of_date() -> None:
    base = status("A")
    broken = replace(
        base,
        target=replace(base.target, mirror_path="/proton/a"),
        last_mirror_at=NOON,
        mirror_error="not signed in",
        mirror_overdue=True,
    )
    result = protection([broken])
    assert "A: the copy on Proton Drive failed: not signed in" in _messages(result, Severity.ALERT)
    assert not any("out of date" in m for m in _messages(result, Severity.WARNING))


def test_a_place_not_connected_for_a_while_names_the_day_it_was_last_tried() -> None:
    away = status("Disk", overdue=True, skipped_since=datetime(2026, 10, 3, 2, 30, tzinfo=UTC))
    result = protection([away, status("B")])
    assert (
        Problem(
            Severity.WARNING,
            "Disk has not been connected since 03 Oct 2026: "
            "connect it and the backup starts by itself.",
            away.target.id,
        )
        in result.problems
    )
    assert "Disk: the backup is overdue." not in _messages(result, Severity.WARNING)


def test_an_overdue_place_that_was_not_skipped_is_called_overdue() -> None:
    late = status("Disk", overdue=True)
    result = protection([late, status("B")])
    assert Problem(Severity.WARNING, "Disk: the backup is overdue.", late.target.id) in (
        result.problems
    )


def test_an_overdue_place_that_also_failed_is_not_called_overdue_too() -> None:
    both = status("Disk", overdue=True, last_run=_failed_run("boom"))
    result = protection([both, status("B")])
    assert "Disk: the backup is overdue." not in _messages(result, Severity.WARNING)


def test_a_stale_proton_copy_warns_that_it_catches_up_online() -> None:
    base = status("A")
    stale = replace(
        base,
        target=replace(base.target, mirror_path="/proton/a"),
        last_mirror_at=NOON,
        mirror_overdue=True,
    )
    result = protection([stale])
    assert (
        Problem(
            Severity.WARNING,
            "A: the copy on Proton Drive is out of date; "
            "it catches up when this computer is online.",
            stale.target.id,
        )
        in result.problems
    )
    assert _messages(result, Severity.ALERT) == ["Only 1 of 2 backup places is up to date."]


def test_an_unsaved_recovery_key_warns() -> None:
    base = status("A")
    unsaved = replace(base, target=replace(base.target, key_saved_at=None))
    result = protection([unsaved, status("B")])
    assert (
        Problem(
            Severity.WARNING,
            "A: the recovery key is not saved yet. Without it this backup cannot be read.",
            unsaved.target.id,
        )
        in result.problems
    )


def test_a_skipped_place_that_is_not_overdue_raises_nothing() -> None:
    away = status("Disk", skipped_since=NOON)
    result = protection([away, status("B")])
    assert result.problems == ()
    assert result.protected


def _manual(**overrides: Any) -> TargetStatus:
    base = status("Disk", **overrides)
    return replace(base, target=replace(base.target, schedule="manual"))


def test_a_manual_place_that_was_skipped_is_not_a_healthy_place() -> None:
    away = _manual(skipped_since=NOON)
    result = protection([away, status("B")])
    assert (result.places_ok, result.places_total) == (1, 2)
    assert (
        Problem(
            Severity.WARNING,
            "Disk was not connected at its last backup: connect it and run the backup again.",
            away.target.id,
        )
        in result.problems
    )
    assert _messages(result, Severity.ALERT) == ["Only 1 of 2 backup places is up to date."]


def test_two_manual_places_that_were_skipped_are_not_protected() -> None:
    result = protection([_manual(skipped_since=NOON), _manual(skipped_since=NOON)])
    assert not result.protected and result.places_ok == 0


def test_a_manual_place_that_was_not_skipped_stays_healthy_and_quiet() -> None:
    result = protection([_manual(), status("B")])
    assert result.protected and result.problems == ()


def test_alerts_come_before_warnings() -> None:
    base = status("A")
    unsaved = replace(base, target=replace(base.target, key_saved_at=None))
    failing = status("B", last_run=_failed_run("boom"))
    result = protection([unsaved, failing])
    assert [p.severity for p in result.problems] == [
        Severity.ALERT,
        Severity.ALERT,
        Severity.WARNING,
    ]
    assert result.problems[0].target_id is None, "library-wide rows come first"
    assert result.problems[-1].target_id == unsaved.target.id


_SLOT = parse_schedule("daily 02:30")
_NIGHT = parse_window("01:00-05:00")


def test_a_skipped_run_is_retried_only_after_fifteen_minutes() -> None:
    assert timedelta(minutes=15) == SKIP_RETRY
    assert probe_allowed(None, NOON)
    assert not probe_allowed(NOON - timedelta(minutes=14, seconds=59), NOON)
    assert probe_allowed(NOON - timedelta(minutes=15), NOON)


def test_catching_up_ignores_the_quiet_window_and_a_normal_run_does_not() -> None:
    last = datetime(2026, 10, 1, 2, 30)
    midday = datetime(2026, 10, 3, 12, 0)
    assert not backup_due(_SLOT, last, midday, _NIGHT, catching_up=False)
    assert backup_due(_SLOT, last, midday, _NIGHT, catching_up=True)


def test_nothing_is_due_before_the_next_slot_even_when_catching_up() -> None:
    last = datetime(2026, 10, 1, 2, 30)
    before_slot = datetime(2026, 10, 2, 2, 29)
    assert not backup_due(_SLOT, last, before_slot, _NIGHT, catching_up=True)
