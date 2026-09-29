from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.capture_time import (
    CaptureTime,
    DateSource,
    MetadataDates,
    date_from_filename,
    parse_exif_datetime,
    parse_offset,
    pick_capture_time,
)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
MTIME = datetime(2025, 3, 7, 11, 34, 12, tzinfo=UTC)


# --- parse_exif_datetime -------------------------------------------------------------------


def test_parses_standard_exif_format() -> None:
    assert parse_exif_datetime("2017:02:20 08:59:21") == (datetime(2017, 2, 20, 8, 59, 21), None)


def test_parses_inline_offset_and_subseconds() -> None:
    value, offset = parse_exif_datetime("2019:07:04 18:30:00.123+02:00")  # type: ignore[misc]
    assert value == datetime(2019, 7, 4, 18, 30, 0)
    assert offset == 120


@pytest.mark.parametrize(
    "raw",
    ["0000:00:00 00:00:00", "", "    :  :     :  :  ", "2017:13:01 00:00:00", "garbage", None],
)
def test_placeholder_or_broken_dates_are_rejected(raw: str | None) -> None:
    assert parse_exif_datetime(raw) is None


# --- date_from_filename --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("20251108_100559.jpg", datetime(2025, 11, 8, 10, 5, 59)),
        ("IMG_20190704_183000.jpg", datetime(2019, 7, 4, 18, 30, 0)),
        ("PXL_20230101_120000123.jpg", datetime(2023, 1, 1, 12, 0, 0)),
        ("2015-02-02 15.53.11.jpeg", datetime(2015, 2, 2, 15, 53, 11)),
        ("Screenshot from 2026-07-03 15-21-27.png", datetime(2026, 7, 3, 15, 21, 27)),
        ("Screenshot_20200101-123456.png", datetime(2020, 1, 1, 12, 34, 56)),
        ("WhatsApp Image 2020-10-26 at 12.34.56.jpeg", datetime(2020, 10, 26, 12, 34, 56)),
        ("VID-20200101-WA0001.jpg", datetime(2020, 1, 1)),
    ],
)
def test_dates_embedded_in_common_file_names(name: str, expected: datetime) -> None:
    assert date_from_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "IMG_1234.JPG",
        "10174880_903634589713690_321783628180766947_n.jpg",  # Facebook id, not a date
        "12312423412.jpg",
        "20251399_100559.jpg",  # month 13
        "GOPR4732.JPG",
    ],
)
def test_names_without_a_real_date_give_nothing(name: str) -> None:
    assert date_from_filename(name) is None


# --- pick_capture_time: the fallback chain -------------------------------------------------


def pick(dates: MetadataDates, name: str = "IMG_1.JPG") -> CaptureTime:
    return pick_capture_time(dates, filename=name, file_mtime=MTIME, now=NOW)


def test_exif_original_wins_over_everything() -> None:
    result = pick(
        MetadataDates(date_time_original="2017:02:20 08:59:21", create_date="2018:01:01 00:00:00"),
        name="20251108_100559.jpg",
    )
    assert result == CaptureTime(datetime(2017, 2, 20, 8, 59, 21), None, DateSource.EXIF)


def test_offset_tag_is_kept_as_minutes() -> None:
    result = pick(MetadataDates(date_time_original="2017:02:20 08:59:21", offset_time="-05:00"))
    assert result.tz_offset_minutes == -300


def test_create_date_is_second_choice() -> None:
    result = pick(MetadataDates(create_date="2018:01:01 10:00:00"))
    assert result.source is DateSource.EXIF_CREATE


def test_xmp_date_is_third_choice() -> None:
    result = pick(MetadataDates(xmp_date_created="2016-05-01T10:00:00"))
    assert result == CaptureTime(datetime(2016, 5, 1, 10), None, DateSource.XMP)


def test_filename_is_used_when_metadata_has_no_date() -> None:
    result = pick(MetadataDates(), name="2015-02-02 15.53.11.jpeg")
    assert result == CaptureTime(datetime(2015, 2, 2, 15, 53, 11), None, DateSource.FILENAME)


def test_file_mtime_is_the_last_resort_and_says_so() -> None:
    result = pick(MetadataDates(), name="12312423412.jpg")
    assert result.source is DateSource.FILE_MTIME
    assert result.value == datetime(2025, 3, 7, 11, 34, 12)
    assert result.tz_offset_minutes == 0


def test_future_dates_are_distrusted() -> None:
    future = (NOW + timedelta(days=3)).strftime("%Y:%m:%d %H:%M:%S")
    result = pick(MetadataDates(date_time_original=future, create_date="2018:01:01 10:00:00"))
    assert result.source is DateSource.EXIF_CREATE


def test_dates_before_photography_are_distrusted() -> None:
    result = pick(MetadataDates(date_time_original="1800:01:01 00:00:00"), name="IMG_1.JPG")
    assert result.source is DateSource.FILE_MTIME


@given(
    exif=st.one_of(st.none(), st.text(max_size=30)),
    create=st.one_of(st.none(), st.text(max_size=30)),
    name=st.text(max_size=60),
)
def test_always_returns_a_plausible_date_whatever_the_input(
    exif: str | None, create: str | None, name: str
) -> None:
    result = pick(MetadataDates(date_time_original=exif, create_date=create), name=name)
    assert datetime(1826, 1, 1) <= result.value <= NOW.replace(tzinfo=None) + timedelta(days=1)


@pytest.mark.parametrize(
    ("raw", "minutes"), [("Z", 0), ("+0530", 330), ("-03:30", -210), ("junk", None), ("", None)]
)
def test_offsets(raw: str, minutes: int | None) -> None:
    assert parse_offset(raw) == minutes
