"""Backup value types: retention, target validation, restore-test summaries."""

import pytest

from photo_assistant.domain.backup import (
    NewBackupTarget,
    RestoreCheck,
    RestoreTestReport,
    Retention,
    TargetKind,
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
    values = {"label": "Disk", "repository": "/r", "password_file": "/p"} | overrides
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
