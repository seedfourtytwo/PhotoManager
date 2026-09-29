"""Backup schedules (FEATURES 9b.3), as pure functions on local wall-clock time.

The language is deliberately tiny, so a busy person can type it and read it back:

    manual              only when asked
    hourly              at every full hour
    daily 02:30         every day at 02:30
    weekly sun 03:00    every Sunday at 03:00

A quiet window ("22:00-06:00", may cross midnight) is when scheduled runs are *allowed*: the
hours nobody uses the laptop. A slot outside it waits for the window to open.

All datetimes here are naive local wall-clock times; the app layer converts. Working on the
wall clock means "02:30" stays 02:30 across daylight-saving changes.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum


class InvalidScheduleError(ValueError):
    """A schedule or quiet window the user typed that we cannot understand."""


class Every(StrEnum):
    MANUAL = "manual"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_INTERVALS = {
    Every.HOURLY: timedelta(hours=1),
    Every.DAILY: timedelta(days=1),
    Every.WEEKLY: timedelta(days=7),
}
_HELP = "use 'manual', 'hourly', 'daily HH:MM' or 'weekly sun HH:MM'"


@dataclass(frozen=True, slots=True)
class Schedule:
    every: Every
    at: time = time(0, 0)
    weekday: int = 0  # Monday = 0, as datetime.weekday()

    @property
    def interval(self) -> timedelta | None:
        return _INTERVALS.get(self.every)

    def __str__(self) -> str:
        clock = f"{self.at:%H:%M}"
        if self.every is Every.DAILY:
            return f"daily {clock}"
        if self.every is Every.WEEKLY:
            return f"weekly {WEEKDAYS[self.weekday]} {clock}"
        return self.every.value


@dataclass(frozen=True, slots=True)
class QuietWindow:
    """[start, end) in local time; end before start means the window crosses midnight."""

    start: time
    end: time

    def contains(self, moment: datetime) -> bool:
        clock = moment.time()
        if self.start < self.end:
            return self.start <= clock < self.end
        return clock >= self.start or clock < self.end

    def next_opening(self, moment: datetime) -> datetime:
        """``moment`` itself if inside the window, else the next time the window opens."""
        if self.contains(moment):
            return moment
        opening = moment.replace(
            hour=self.start.hour, minute=self.start.minute, second=0, microsecond=0
        )
        return opening if opening > moment else opening + timedelta(days=1)

    def __str__(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M}"


def _parse_clock(text: str, what: str) -> time:
    hours, sep, minutes = text.partition(":")
    if not sep or not hours.isdigit() or not minutes.isdigit() or len(minutes) != 2:
        raise InvalidScheduleError(f"bad time {text!r} in {what}: write it as HH:MM")
    if int(hours) > 23 or int(minutes) > 59:
        raise InvalidScheduleError(f"time out of range {text!r} in {what}")
    return time(int(hours), int(minutes))


def parse_schedule(text: str) -> Schedule:
    words = text.lower().split()
    what = f"schedule {text!r}"
    match words:
        case ["manual"]:
            return Schedule(Every.MANUAL)
        case ["hourly"]:
            return Schedule(Every.HOURLY)
        case ["daily", clock]:
            return Schedule(Every.DAILY, _parse_clock(clock, what))
        case ["weekly", day, clock] if day in WEEKDAYS:
            return Schedule(Every.WEEKLY, _parse_clock(clock, what), WEEKDAYS.index(day))
    raise InvalidScheduleError(f"unknown schedule {text!r}: {_HELP}")


def parse_window(text: str | None) -> QuietWindow | None:
    """``None`` or blank means "any time"."""
    if text is None or not text.strip():
        return None
    what = f"quiet window {text!r}"
    start, sep, end = text.strip().partition("-")
    if not sep:
        raise InvalidScheduleError(f"{what} must look like 22:00-06:00")
    window = QuietWindow(_parse_clock(start.strip(), what), _parse_clock(end.strip(), what))
    if window.start == window.end:
        raise InvalidScheduleError(f"{what} is empty: start and end are the same")
    return window


def _next_slot(schedule: Schedule, after: datetime) -> datetime:
    if schedule.every is Every.HOURLY:
        return after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    slot = after.replace(hour=schedule.at.hour, minute=schedule.at.minute, second=0, microsecond=0)
    if schedule.every is Every.WEEKLY:
        slot += timedelta(days=(schedule.weekday - after.weekday()) % 7)
        step = timedelta(days=7)
    else:
        step = timedelta(days=1)
    return slot if slot > after else slot + step


def next_run(
    schedule: Schedule, after: datetime, window: QuietWindow | None = None
) -> datetime | None:
    """The first scheduled moment strictly after ``after``, moved into the quiet window."""
    if schedule.every is Every.MANUAL:
        return None
    slot = _next_slot(schedule, after)
    return slot if window is None else window.next_opening(slot)


def is_due(
    schedule: Schedule,
    last_attempt: datetime,
    now: datetime,
    window: QuietWindow | None = None,
) -> bool:
    """True when a slot after the last attempt has passed and we are inside the window.

    A laptop that was off for days runs once when it wakes, not once per missed slot."""
    upcoming = next_run(schedule, last_attempt, window)
    if upcoming is None or upcoming > now:
        return False
    return window is None or window.contains(now)


def is_overdue(
    schedule: Schedule, last_success: datetime | None, since: datetime, now: datetime
) -> bool:
    """No success within two intervals (counting from ``since`` if there never was one)."""
    interval = schedule.interval
    if interval is None:
        return False
    return now - (last_success or since) > 2 * interval
