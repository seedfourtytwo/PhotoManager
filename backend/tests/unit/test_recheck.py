"""When a source checks itself again (issues 7 and 8): off, or every hour, day or week."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.domain.recheck import Recheck, is_due, next_check_at
from tests.factories import NOW


@pytest.mark.parametrize(
    ("recheck", "interval"),
    [
        (Recheck.HOURLY, timedelta(hours=1)),
        (Recheck.DAILY, timedelta(days=1)),
        (Recheck.WEEKLY, timedelta(days=7)),
    ],
)
def test_a_source_is_due_once_its_interval_has_passed_since_the_last_check(
    recheck: Recheck, interval: timedelta
) -> None:
    second = timedelta(seconds=1)
    assert not is_due(recheck, True, NOW - interval + second, NOW)
    assert is_due(recheck, True, NOW - interval, NOW), "exactly the interval ago is due"
    assert is_due(recheck, True, NOW - 3 * interval, NOW), "long overdue is due once"
    assert next_check_at(recheck, True, NOW - second, NOW) == NOW - second + interval


@pytest.mark.parametrize("last_check", [None, NOW - timedelta(days=365)])
def test_a_source_set_to_off_is_never_due(last_check: datetime | None) -> None:
    assert not is_due(Recheck.OFF, True, last_check, NOW)
    assert next_check_at(Recheck.OFF, True, last_check, NOW) is None


def test_a_disabled_source_is_never_due() -> None:
    assert not is_due(Recheck.HOURLY, False, None, NOW)
    assert next_check_at(Recheck.HOURLY, False, NOW - timedelta(days=2), NOW) is None


def test_a_source_that_was_never_checked_is_due_now() -> None:
    assert is_due(Recheck.WEEKLY, True, None, NOW)
    assert next_check_at(Recheck.WEEKLY, True, None, NOW) == NOW


def test_only_the_four_settings_exist() -> None:
    assert [r.value for r in Recheck] == ["off", "hourly", "daily", "weekly"]
    with pytest.raises(ValueError):
        Recheck("monthly")
