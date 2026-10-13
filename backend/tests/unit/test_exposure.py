"""Exposure settings as cameras write them: numbers, fractions, text with units, lists, junk."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.exposure import (
    MAX_EXPOSURE_SECONDS,
    MAX_F_NUMBER,
    MAX_FOCAL_LENGTH_MM,
    MAX_ISO,
    Exposure,
    parse_exposure_time,
    parse_f_number,
    parse_focal_length,
    parse_iso,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(2.8, 2.8), (4, 4.0), ("2.8", 2.8), ("f/2.8", 2.8), ("F2.8", 2.8), ("28/10", 2.8), ("f/8", 8)],
)
def test_f_number_reads_numbers_text_and_fractions(raw: object, expected: float) -> None:
    assert parse_f_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw", [None, "", 0, 0.0, "0", "0/1", "28/0", -2.8, "junk", "inf", math.nan, True, 5000]
)
def test_f_number_is_none_for_zero_missing_junk_and_absurd_values(raw: object) -> None:
    assert parse_f_number(raw) is None


def test_f_number_is_kept_to_two_decimals() -> None:
    assert parse_f_number(1.7999999523162842) == 1.8  # what a camera's "9/5" reads back as


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.004, 0.004),
        ("1/250", 0.004),
        (2.5, 2.5),
        (30, 30.0),
        ("30", 30.0),
        ("10/4", 2.5),
        ("1/250 s", 0.004),
        ("2.5 sec", 2.5),
    ],
)
def test_exposure_time_is_seconds_from_numbers_text_and_fractions(
    raw: object, expected: float
) -> None:
    assert parse_exposure_time(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw", [None, "", 0, "0", "0/250", "1/0", -1, "fast", math.inf, MAX_EXPOSURE_SECONDS + 1]
)
def test_exposure_time_is_none_for_zero_missing_junk_and_absurd_values(raw: object) -> None:
    assert parse_exposure_time(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(400, 400), ("400", 400), (400.0, 400), ("ISO 400", 400), (64.4, 64), (1, 1)],
)
def test_iso_is_a_whole_number(raw: object, expected: int) -> None:
    assert parse_iso(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([200, 400], 200),
        ((0, 800), 800),
        ("100 200", 100),
        ("0, 320", 320),
        (["junk", "1600"], 1600),
    ],
)
def test_iso_given_several_values_takes_the_first_sensible_one(raw: object, expected: int) -> None:
    assert parse_iso(raw) == expected


@pytest.mark.parametrize(
    "raw", [None, "", 0, -100, "auto", [], [0, "x"], True, MAX_ISO + 1, 65535 * 65536, math.nan]
)
def test_iso_is_none_for_zero_missing_junk_and_absurd_values(raw: object) -> None:
    assert parse_iso(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (35.0, 35.0),
        (35, 35.0),
        ("35.0 mm", 35.0),
        ("35mm", 35.0),
        ("425/100", 4.25),
        ("4.25", 4.25),
    ],
)
def test_focal_length_is_millimetres(raw: object, expected: float) -> None:
    assert parse_focal_length(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", 0, "0.0 mm", "35/0", -35, "wide", 1e9])
def test_focal_length_is_none_for_zero_missing_junk_and_absurd_values(raw: object) -> None:
    assert parse_focal_length(raw) is None


def test_exposure_from_raw_keeps_what_reads_and_drops_what_does_not() -> None:
    exposure = Exposure.from_raw(
        f_number="f/2.8", exposure_time="1/250", iso=[0, 400], focal_length="junk"
    )
    assert exposure == Exposure(2.8, 0.004, 400, None)
    assert not exposure.is_empty


def test_an_exposure_with_nothing_readable_is_empty() -> None:
    assert Exposure.from_raw(f_number=0, exposure_time=None, iso="auto", focal_length="").is_empty
    assert Exposure().is_empty


# --- properties ------------------------------------------------------------------------------

_anything = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=True, allow_infinity=True),
        st.text(max_size=12),
        st.binary(max_size=4),
    ),
    lambda inner: st.lists(inner, max_size=3),
    max_leaves=6,
)


@given(_anything)
def test_no_input_raises_and_every_result_is_within_its_limits(raw: object) -> None:
    f, t, focal, iso = (
        parse_f_number(raw),
        parse_exposure_time(raw),
        parse_focal_length(raw),
        parse_iso(raw),
    )
    assert f is None or 0 < f <= MAX_F_NUMBER
    assert t is None or 0 < t <= MAX_EXPOSURE_SECONDS
    assert focal is None or 0 < focal <= MAX_FOCAL_LENGTH_MM
    assert iso is None or 1 <= iso <= MAX_ISO


@given(st.integers(1, 100_000), st.integers(1, 100_000))
def test_a_fraction_reads_as_its_quotient(top: int, bottom: int) -> None:
    value = top / bottom
    expected = value if value <= MAX_EXPOSURE_SECONDS else None
    assert parse_exposure_time(f"{top}/{bottom}") == expected


@given(st.floats(min_value=1 / 64000, max_value=MAX_EXPOSURE_SECONDS, allow_nan=False))
def test_a_number_and_its_text_read_the_same(seconds: float) -> None:
    assert parse_exposure_time(repr(seconds)) == parse_exposure_time(seconds) == seconds


@given(st.integers(1, MAX_ISO))
def test_every_iso_within_the_limit_reads_back_as_itself(iso: int) -> None:
    assert parse_iso(iso) == parse_iso(str(iso)) == parse_iso([iso, 100]) == iso


@given(st.floats(min_value=0.5, max_value=MAX_F_NUMBER, allow_nan=False))
def test_reading_a_stored_exposure_again_changes_nothing(value: float) -> None:
    once = Exposure.from_raw(f_number=value, exposure_time=value, iso=value, focal_length=value)
    again = Exposure.from_raw(
        f_number=once.f_number,
        exposure_time=once.exposure_time,
        iso=once.iso,
        focal_length=once.focal_length,
    )
    assert again == once
