"""Backup schedules (FEATURES 9b.3): parsing, next run, quiet window, due and overdue."""

from datetime import datetime, time, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.schedule import (
    Every,
    InvalidScheduleError,
    QuietWindow,
    Schedule,
    is_due,
    is_overdue,
    next_run,
    parse_schedule,
    parse_window,
)

# 2026-09-29 is a Tuesday
TUE_10 = datetime(2026, 9, 29, 10, 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("manual", Schedule(Every.MANUAL)),
        ("hourly", Schedule(Every.HOURLY)),
        ("daily 02:30", Schedule(Every.DAILY, time(2, 30))),
        ("  Daily   2:05 ", Schedule(Every.DAILY, time(2, 5))),
        ("weekly sun 03:00", Schedule(Every.WEEKLY, time(3, 0), weekday=6)),
        ("weekly MON 23:59", Schedule(Every.WEEKLY, time(23, 59), weekday=0)),
    ],
)
def test_parses_the_simple_schedule_language(text: str, expected: Schedule) -> None:
    assert parse_schedule(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "sometimes",
        "daily",
        "daily 24:00",
        "daily 12:60",
        "daily noon",
        "weekly 03:00",
        "weekly sunday 03:00",
        "hourly 02:00",
        "manual now",
        "daily 1:2:3",
    ],
)
def test_rejects_anything_else_with_a_helpful_message(text: str) -> None:
    with pytest.raises(InvalidScheduleError, match="schedule"):
        parse_schedule(text)


@pytest.mark.parametrize("text", ["manual", "hourly", "daily 02:30", "weekly sun 03:00"])
def test_canonical_text_round_trips(text: str) -> None:
    assert str(parse_schedule(text)) == text


def test_intervals() -> None:
    assert parse_schedule("manual").interval is None
    assert parse_schedule("hourly").interval == timedelta(hours=1)
    assert parse_schedule("daily 01:00").interval == timedelta(days=1)
    assert parse_schedule("weekly sat 01:00").interval == timedelta(days=7)


def test_manual_never_runs_by_itself() -> None:
    assert next_run(parse_schedule("manual"), TUE_10) is None


def test_hourly_runs_at_the_next_full_hour() -> None:
    assert next_run(parse_schedule("hourly"), datetime(2026, 9, 29, 10, 20)) == datetime(
        2026, 9, 29, 11, 0
    )
    assert next_run(parse_schedule("hourly"), TUE_10) == datetime(2026, 9, 29, 11, 0)


def test_daily_runs_later_today_or_tomorrow() -> None:
    assert next_run(parse_schedule("daily 14:00"), TUE_10) == datetime(2026, 9, 29, 14, 0)
    assert next_run(parse_schedule("daily 02:30"), TUE_10) == datetime(2026, 9, 30, 2, 30)
    assert next_run(parse_schedule("daily 10:00"), TUE_10) == datetime(2026, 9, 30, 10, 0)


def test_weekly_runs_on_the_named_day() -> None:
    assert next_run(parse_schedule("weekly sun 03:00"), TUE_10) == datetime(2026, 10, 4, 3, 0)
    assert next_run(parse_schedule("weekly tue 11:00"), TUE_10) == datetime(2026, 9, 29, 11, 0)
    assert next_run(parse_schedule("weekly tue 09:00"), TUE_10) == datetime(2026, 10, 6, 9, 0)


def test_quiet_window_across_midnight() -> None:
    window = QuietWindow(time(22, 0), time(6, 0))
    assert window.contains(datetime(2026, 9, 29, 23, 0))
    assert window.contains(datetime(2026, 9, 29, 5, 59))
    assert not window.contains(datetime(2026, 9, 29, 6, 0))
    assert not window.contains(TUE_10)
    assert window.next_opening(TUE_10) == datetime(2026, 9, 29, 22, 0)
    assert window.next_opening(datetime(2026, 9, 29, 23, 0)) == datetime(2026, 9, 29, 23, 0)
    assert window.next_opening(datetime(2026, 9, 29, 22, 30)) == datetime(2026, 9, 29, 22, 30)


def test_quiet_window_within_one_day() -> None:
    window = QuietWindow(time(12, 0), time(14, 0))
    assert window.contains(datetime(2026, 9, 29, 13, 0))
    assert not window.contains(datetime(2026, 9, 29, 14, 0))
    assert window.next_opening(datetime(2026, 9, 29, 15, 0)) == datetime(2026, 9, 30, 12, 0)


def test_runs_outside_the_window_wait_for_it_to_open() -> None:
    window = parse_window("22:00-06:00")
    hourly = parse_schedule("hourly")
    assert next_run(hourly, TUE_10, window) == datetime(2026, 9, 29, 22, 0)
    assert next_run(hourly, datetime(2026, 9, 29, 23, 5), window) == datetime(2026, 9, 30, 0, 0)
    assert next_run(parse_schedule("daily 02:30"), TUE_10, window) == datetime(2026, 9, 30, 2, 30)


def test_parse_window() -> None:
    assert parse_window(None) is None
    assert parse_window("  ") is None
    assert parse_window("22:00-06:00") == QuietWindow(time(22, 0), time(6, 0))
    assert str(QuietWindow(time(22, 0), time(6, 0))) == "22:00-06:00"
    for bad in ("22:00", "22:00-22:00", "a-b", "25:00-01:00"):
        with pytest.raises(InvalidScheduleError, match="window"):
            parse_window(bad)


def test_due_when_the_next_slot_has_passed() -> None:
    daily = parse_schedule("daily 02:30")
    last = datetime(2026, 9, 28, 2, 30)
    assert not is_due(daily, last, datetime(2026, 9, 29, 2, 29))
    assert is_due(daily, last, datetime(2026, 9, 29, 2, 30))
    assert is_due(daily, last, datetime(2026, 10, 3, 9, 0)), "laptop was off: catch up once"
    assert not is_due(parse_schedule("manual"), last, datetime(2030, 1, 1))


def test_never_due_outside_the_quiet_window() -> None:
    hourly = parse_schedule("hourly")
    window = parse_window("22:00-06:00")
    last = datetime(2026, 9, 28, 23, 0)
    assert not is_due(hourly, last, TUE_10, window), "a missed slot waits for the window"
    assert is_due(hourly, last, datetime(2026, 9, 29, 22, 1), window)


def test_overdue_after_two_intervals_without_success() -> None:
    daily = parse_schedule("daily 02:30")
    created = datetime(2026, 9, 1)
    assert not is_overdue(daily, datetime(2026, 9, 28, 2, 30), created, datetime(2026, 9, 30, 2, 0))
    assert is_overdue(daily, datetime(2026, 9, 28, 2, 30), created, datetime(2026, 9, 30, 3, 0))
    assert is_overdue(daily, None, created, datetime(2026, 9, 3, 1, 0)), "never succeeded"
    assert not is_overdue(daily, None, created, datetime(2026, 9, 2, 0, 0))
    assert not is_overdue(parse_schedule("manual"), None, created, datetime(2030, 1, 1))


@given(
    after=st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2090, 1, 1)),
    text=st.sampled_from(["hourly", "daily 02:30", "daily 00:00", "weekly sun 03:00"]),
    window=st.sampled_from([None, "22:00-06:00", "01:00-03:00"]),
)
def test_next_run_is_always_later_within_a_week_and_inside_the_window(
    after: datetime, text: str, window: str | None
) -> None:
    quiet = parse_window(window)
    result = next_run(parse_schedule(text), after, quiet)
    assert result is not None
    assert after < result <= after + timedelta(days=8)
    assert quiet is None or quiet.contains(result)
