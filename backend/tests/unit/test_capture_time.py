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


# --- QA M1 --------------------------------------------------------------------------------


def test_mtime_fallback_keeps_the_local_wall_clock_and_offset() -> None:
    """Regression: 00:30 on 1 Jan in France was stored as 22:30 on 31 Dec (UTC)."""
    from datetime import timezone

    paris_winter = timezone(timedelta(hours=1))
    mtime = datetime(2020, 1, 1, 0, 30, tzinfo=paris_winter)
    result = pick_capture_time(MetadataDates(), filename="x.jpg", file_mtime=mtime, now=NOW)
    assert result == CaptureTime(datetime(2020, 1, 1, 0, 30), 60, DateSource.FILE_MTIME)


def test_future_mtime_is_clamped_to_now() -> None:
    later = NOW + timedelta(days=30)
    result = pick_capture_time(MetadataDates(), filename="x.jpg", file_mtime=later, now=NOW)
    assert result.value == NOW.replace(tzinfo=None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2019:07:04", datetime(2019, 7, 4)), ("2019-07-04", datetime(2019, 7, 4))],
)
def test_date_only_metadata_is_accepted_as_midnight(raw: str, expected: datetime) -> None:
    assert parse_exif_datetime(raw) == (expected, None)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("signal-2021-05-01-12-34-56-789.jpg", datetime(2021, 5, 1, 12, 34, 56)),
        ("FB_IMG_1591234567890.jpg", datetime(2020, 6, 4, 1, 36, 7)),
        ("mmexport1591234567890.jpg", datetime(2020, 6, 4, 1, 36, 7)),
        ("scan_2019-07-04.jpg", datetime(2019, 7, 4)),
        ("DSC_20190704.JPG", datetime(2019, 7, 4)),
        ("holiday 2019-07-04 beach.jpg", datetime(2019, 7, 4)),
        ("IMG_20191340_2019-07-04.jpg", datetime(2019, 7, 4)),  # first match impossible
    ],
)
def test_more_real_world_file_name_dates(name: str, expected: datetime) -> None:
    assert date_from_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "IMG_5215 - Copy.JPG",
        "IMG_0027(1).HEIC",
        "12524245_10208913554978036_5455922839164665818_n.jpg",
        "15602_10206188729539103_7594325285226378834_n.jpg",
        "122687643_4494779827260372_3856678087240746241_n.jpg",
        "20190704123.jpg",  # digits run on: not a date
    ],
)
def test_still_no_false_positives(name: str) -> None:
    assert date_from_filename(name) is None


def test_facebook_id_that_looks_like_a_date_is_not_a_date() -> None:
    """Second review: 20151012_903634589713690_n.jpg is a Facebook id, not 12 Oct 2015."""
    assert date_from_filename("20151012_903634589713690_n.jpg") is None


def test_epoch_names_become_local_wall_clock_time() -> None:
    """FB_IMG_1577835000000 = 2019-12-31 23:30 UTC = 2020-01-01 00:30 in Paris (winter)."""
    from datetime import timezone

    paris = timezone(timedelta(hours=1))
    mtime = datetime(2024, 1, 1, tzinfo=paris)
    result = pick_capture_time(
        MetadataDates(), filename="FB_IMG_1577835000000.jpg", file_mtime=mtime, now=NOW
    )
    assert result == CaptureTime(datetime(2020, 1, 1, 0, 30), 60, DateSource.FILENAME)


def test_a_time_from_the_file_mtime_is_whole_seconds_like_every_other_source() -> None:
    """QA A12: mtime dates were stored with microseconds."""
    mtime = datetime(2020, 5, 1, 10, 0, 7, 729120, tzinfo=UTC)
    result = pick_capture_time(MetadataDates(), filename="x.jpg", file_mtime=mtime, now=NOW)
    assert result.value == datetime(2020, 5, 1, 10, 0, 7)
    assert result.value.microsecond == 0


# --- review round 3: 12-hour clocks, compact times, one plausibility rule for names -----------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Screenshot 2024-03-10 at 9.15.22 AM.png", datetime(2024, 3, 10, 9, 15, 22)),
        ("Screenshot 2024-03-10 at 9.15.22 PM.png", datetime(2024, 3, 10, 21, 15, 22)),
        ("Screenshot 2024-03-10 at 9.15.22\u202fPM.png", datetime(2024, 3, 10, 21, 15, 22)),
        ("Screenshot 2024-03-10 at 12.05.00 AM.png", datetime(2024, 3, 10, 0, 5, 0)),
        ("Screenshot 2024-03-10 at 12.05.00 pm.png", datetime(2024, 3, 10, 12, 5, 0)),
        ("Screenshot 2024-03-10 at 9.15.22.png", datetime(2024, 3, 10, 9, 15, 22)),
        ("Screenshot 2024-03-10 at 21.15.22.png", datetime(2024, 3, 10, 21, 15, 22)),
        ("Screenshot 2024-03-10 at 13.15.22 PM.png", datetime(2024, 3, 10, 13, 15, 22)),
        ("2015-02-02 10.53.11 Amsterdam.jpg", datetime(2015, 2, 2, 10, 53, 11)),  # not "AM"
        ("2015-02-02 10.53.11 pm Amsterdam.jpg", datetime(2015, 2, 2, 22, 53, 11)),
        ("signal-2021-05-01-123456.jpg", datetime(2021, 5, 1, 12, 34, 56)),
        ("signal-2021-05-01-123456789.jpg", datetime(2021, 5, 1)),  # digits run on: no time
    ],
)
def test_twelve_hour_and_compact_times_in_file_names(name: str, expected: datetime) -> None:
    assert date_from_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "1080-1920-01-02.jpg",  # a picture size glued to digits: not 2 January 1920
        "19200102.jpg",
        "18990704_120000.jpg",
        "2100-01-01.jpg",
        "1825-12-31.jpg",  # before the first photograph
    ],
)
def test_digits_that_are_too_often_something_else_are_not_dates(name: str) -> None:
    """Compact dates (YYYYMMDD) are believed in 1990-2099 only; so is a dashed date glued to
    a number group before it. A dashed date standing alone may be as old as photography."""
    assert date_from_filename(name) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("1975-06-01 grandma.jpg", datetime(1975, 6, 1)),
        ("scan 1931-12-24.png", datetime(1931, 12, 24)),
        ("1920-01-02.jpg", datetime(1920, 1, 2)),
        ("1962-08-15 14.30.00 wedding.jpg", datetime(1962, 8, 15, 14, 30, 0)),
        ("IMG-1920-1080-2021-05-01.jpg", datetime(2021, 5, 1)),  # glued, but a modern year
        ("1826-01-01.jpg", datetime(1826, 1, 1)),
    ],
)
def test_scans_named_with_an_old_dashed_date_keep_it(name: str, expected: datetime) -> None:
    """Regression: one 1990-2099 range for every spelling took the date off scanned family
    photos, which then fell back to the day they were scanned."""
    assert date_from_filename(name) == expected


def test_an_old_scan_gets_its_date_from_the_name_not_the_file() -> None:
    picked = pick(MetadataDates(), "1975-06-01 grandma.jpg")
    assert picked == CaptureTime(datetime(1975, 6, 1), None, DateSource.FILENAME)
    assert pick(MetadataDates(), "1080-1920-01-02.jpg").source is DateSource.FILE_MTIME


@pytest.mark.parametrize("name", ["1990-01-01.jpg", "19900101.jpg", "19900101_000000.jpg"])
def test_the_strict_year_range_starts_in_1990(name: str) -> None:
    assert date_from_filename(name) == datetime(1990, 1, 1)


def test_the_first_plausible_date_in_a_name_wins_not_the_first_valid_one() -> None:
    assert date_from_filename("1080-1920-01-02 2021-05-01.jpg") == datetime(2021, 5, 1)
    future_first = pick(MetadataDates(), "2090-01-01 copy of 2021-05-01.jpg")
    assert future_first == CaptureTime(datetime(2021, 5, 1), None, DateSource.FILENAME)
    assert pick(MetadataDates(), "2090-01-01.jpg").source is DateSource.FILE_MTIME
