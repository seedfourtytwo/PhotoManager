"""When a source checks itself again (issues 7 and 8), as pure functions.

A source's setting is one of four words. The interval counts from the last *attempt* (the
start of its latest check, whether it worked or not), so a source that keeps failing is tried
once per interval, not over and over.
"""

from datetime import datetime, timedelta
from enum import StrEnum


class Recheck(StrEnum):
    OFF = "off"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


_INTERVALS = {
    Recheck.HOURLY: timedelta(hours=1),
    Recheck.DAILY: timedelta(days=1),
    Recheck.WEEKLY: timedelta(days=7),
}


def next_check_at(
    recheck: Recheck, enabled: bool, last_check: datetime | None, now: datetime
) -> datetime | None:
    """When the source is next checked by itself: None when it never is (off, or disabled),
    ``now`` when it was never checked. A moment in the past means "at the next look"."""
    interval = _INTERVALS.get(recheck)
    if interval is None or not enabled:
        return None
    return now if last_check is None else last_check + interval


def is_due(recheck: Recheck, enabled: bool, last_check: datetime | None, now: datetime) -> bool:
    upcoming = next_check_at(recheck, enabled, last_check, now)
    return upcoming is not None and upcoming <= now
