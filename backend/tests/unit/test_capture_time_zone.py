"""A photo named with a Unix timestamp (FB_IMG_<milliseconds>.jpg) is shown at the local time
of the day it was TAKEN: the offset that applied at that instant, not the offset of the day
the file was saved (which is all the file's modification time carries)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from photo_assistant.domain.capture_time import (
    CaptureTime,
    DateSource,
    MetadataDates,
    pick_capture_time,
)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
BERLIN, TOKYO = ZoneInfo("Europe/Berlin"), ZoneInfo("Asia/Tokyo")
SUMMER_TIME, WINTER_TIME = timezone(timedelta(hours=2)), timezone(timedelta(hours=1))


def _in(zone: ZoneInfo) -> Callable[[datetime], datetime]:
    return lambda moment: moment.astimezone(zone)


def _name(taken_utc: datetime) -> str:
    return f"FB_IMG_{int(taken_utc.timestamp()) * 1000}.jpg"


def _pick(
    taken_utc: datetime, saved: datetime, to_local: Callable[[datetime], datetime] | None
) -> CaptureTime:
    return pick_capture_time(
        MetadataDates(), filename=_name(taken_utc), file_mtime=saved, now=NOW, to_local=to_local
    )


def test_a_winter_photo_saved_in_summer_keeps_its_winter_hour() -> None:
    taken = datetime(2020, 1, 15, 12, 0, tzinfo=UTC)
    saved = datetime(2020, 7, 1, 9, 0, tzinfo=SUMMER_TIME)

    result = _pick(taken, saved, _in(BERLIN))

    assert result == CaptureTime(datetime(2020, 1, 15, 13, 0), 60, DateSource.FILENAME)


def test_a_winter_evening_saved_in_summer_does_not_move_to_the_next_day() -> None:
    taken = datetime(2020, 1, 15, 22, 30, tzinfo=UTC)
    saved = datetime(2020, 7, 1, 9, 0, tzinfo=SUMMER_TIME)

    result = _pick(taken, saved, _in(BERLIN))

    assert result == CaptureTime(datetime(2020, 1, 15, 23, 30), 60, DateSource.FILENAME)


def test_a_summer_photo_saved_in_winter_keeps_its_summer_hour() -> None:
    taken = datetime(2020, 7, 1, 22, 30, tzinfo=UTC)
    saved = datetime(2020, 12, 24, 18, 0, tzinfo=WINTER_TIME)

    result = _pick(taken, saved, _in(BERLIN))

    assert result == CaptureTime(datetime(2020, 7, 2, 0, 30), 120, DateSource.FILENAME)


@pytest.mark.parametrize("saved_month", [1, 7])
def test_a_zone_without_summer_time_gives_the_same_as_before(saved_month: int) -> None:
    taken = datetime(2020, 1, 15, 22, 30, tzinfo=UTC)
    saved = datetime(2020, saved_month, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))

    with_zone = _pick(taken, saved, _in(TOKYO))

    assert with_zone == CaptureTime(datetime(2020, 1, 16, 7, 30), 540, DateSource.FILENAME)
    assert with_zone == _pick(taken, saved, None)


def test_without_a_zone_the_offset_of_the_saved_file_is_all_there_is() -> None:
    """The rule for a caller that knows no zone: unchanged."""
    taken = datetime(2020, 1, 15, 12, 0, tzinfo=UTC)
    saved = datetime(2020, 7, 1, 9, 0, tzinfo=SUMMER_TIME)
    assert _pick(taken, saved, None).value == datetime(2020, 1, 15, 14, 0)


def test_a_date_from_the_files_own_time_is_in_the_zone_at_that_time() -> None:
    saved = datetime(2020, 1, 15, 22, 30, tzinfo=UTC)

    result = pick_capture_time(
        MetadataDates(), filename="x.jpg", file_mtime=saved, now=NOW, to_local=_in(BERLIN)
    )

    assert result == CaptureTime(datetime(2020, 1, 15, 23, 30), 60, DateSource.FILE_MTIME)
