"""Fixing capture dates (FEATURES 2.12): set one time for many photos, or shift them all."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from photo_assistant.domain.capture_time import EARLIEST_PLAUSIBLE


class DateFixError(ValueError):
    """The requested date change can't be applied; the message says why."""


FUTURE_SLACK = timedelta(days=1)  # "now" somewhere on Earth may be a day ahead of the server


def new_capture_times(
    current: Sequence[tuple[int, datetime]],
    set_to: datetime | None,
    shift_minutes: int | None,
    now: datetime,
) -> list[tuple[int, datetime]]:
    """(asset id, new local wall-clock time) for each photo. Exactly one of ``set_to`` and
    ``shift_minutes`` must be given. ``now`` (local wall-clock): no photo may end up more
    than a day after it (QA A11)."""
    latest = now.replace(tzinfo=None) + FUTURE_SLACK
    if (set_to is None) == (shift_minutes is None):
        raise DateFixError("give exactly one of a new date or a shift")
    if set_to is not None:
        target = set_to.replace(tzinfo=None, microsecond=0)
        _check(target, latest)
        return [(asset_id, target) for asset_id, _ in current]
    assert shift_minutes is not None
    result = []
    for asset_id, taken in current:
        try:
            moved = taken + timedelta(minutes=shift_minutes)
        except OverflowError:
            raise DateFixError("that shift moves a photo out of the calendar") from None
        _check(moved, latest)
        result.append((asset_id, moved))
    return result


def _check(value: datetime, latest: datetime) -> None:
    if value < EARLIEST_PLAUSIBLE:
        raise DateFixError(f"dates must be after {EARLIEST_PLAUSIBLE:%Y}: photography began then")
    if value > latest:
        raise DateFixError("a photo can't be taken in the future: pick a date up to today")
