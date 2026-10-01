"""Fixing capture dates (FEATURES 2.12): set one time for many photos, or shift them all."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from photo_assistant.domain.capture_time import EARLIEST_PLAUSIBLE

LATEST = datetime(9999, 12, 31, 23, 59, 59)


class DateFixError(ValueError):
    """The requested date change can't be applied; the message says why."""


def new_capture_times(
    current: Sequence[tuple[int, datetime]], set_to: datetime | None, shift_minutes: int | None
) -> list[tuple[int, datetime]]:
    """(asset id, new local wall-clock time) for each photo. Exactly one of ``set_to`` and
    ``shift_minutes`` must be given."""
    if (set_to is None) == (shift_minutes is None):
        raise DateFixError("give exactly one of a new date or a shift")
    if set_to is not None:
        target = set_to.replace(tzinfo=None, microsecond=0)
        _check(target)
        return [(asset_id, target) for asset_id, _ in current]
    assert shift_minutes is not None
    result = []
    for asset_id, taken in current:
        try:
            moved = taken + timedelta(minutes=shift_minutes)
        except OverflowError:
            raise DateFixError("that shift moves a photo out of the calendar") from None
        _check(moved)
        result.append((asset_id, moved))
    return result


def _check(value: datetime) -> None:
    if not EARLIEST_PLAUSIBLE <= value <= LATEST:
        raise DateFixError(f"dates must be after {EARLIEST_PLAUSIBLE:%Y}: photography began then")
