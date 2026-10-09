"""The look sheet's rules (spec 2026-10-08 §5, docs/adr/0001): unknown fields rejected,
numbers clamped, a broken stored sheet falls back to the defaults."""

import json
import math

import pytest

from photo_assistant.domain.look import (
    DEFAULT_LOOK,
    CollectionsRow,
    Look,
    LookError,
    Mode,
    StartPage,
    Theme,
    ThumbSize,
    dump_look,
    look_sheet,
    parse_look,
    read_look,
)

EVERYTHING = {
    "theme": "album",
    "mode": "light",
    "accentHue": 200,
    "corners": 4,
    "photoGap": 6,
    "textScale": 1.15,
    "thumbSize": "large",
    "showToday": True,
    "startPage": "library",
    "collectionsRows": ["albums", "people"],
    "dockLabels": False,
}


def test_an_empty_sheet_is_the_defaults() -> None:
    assert parse_look({}) == DEFAULT_LOOK


def test_the_defaults_are_the_ones_in_the_spec() -> None:
    assert look_sheet(DEFAULT_LOOK) == {
        "theme": "safelight",
        "mode": "dark",
        "accentHue": None,
        "corners": None,
        "photoGap": None,
        "textScale": 1,
        "thumbSize": "medium",
        "showToday": True,
        "startPage": "today",
        "collectionsRows": ["people", "places", "albums"],
        "dockLabels": True,
    }


def test_every_field_is_read() -> None:
    assert parse_look(EVERYTHING) == Look(
        theme=Theme.ALBUM,
        mode=Mode.LIGHT,
        accent_hue=200,
        corners=4,
        photo_gap=6,
        text_scale=1.15,
        thumb_size=ThumbSize.LARGE,
        show_today=True,
        start_page=StartPage.LIBRARY,
        collections_rows=(CollectionsRow.ALBUMS, CollectionsRow.PEOPLE),
        dock_labels=False,
    )
    assert look_sheet(parse_look(EVERYTHING)) == EVERYTHING


def test_an_unknown_field_is_rejected_by_name() -> None:
    with pytest.raises(LookError, match="'css'"):
        parse_look({"mode": "dark", "css": "body { display: none }"})


@pytest.mark.parametrize(
    ("field", "low", "high"),
    [("accentHue", 0, 360), ("corners", 0, 22), ("photoGap", 0, 8), ("textScale", 0.9, 1.25)],
)
def test_a_number_outside_its_range_is_clamped(field: str, low: float, high: float) -> None:
    assert look_sheet(parse_look({field: low - 100}))[field] == low
    assert look_sheet(parse_look({field: high + 100}))[field] == high
    assert look_sheet(parse_look({field: low}))[field] == low
    assert look_sheet(parse_look({field: high}))[field] == high


def test_a_number_too_large_for_a_float_is_clamped_like_any_other() -> None:
    huge = 10**400  # JSON may carry it; float() of it would overflow
    sheet = look_sheet(parse_look({"accentHue": huge, "corners": -huge, "textScale": huge}))
    assert (sheet["accentHue"], sheet["corners"], sheet["textScale"]) == (360, 0, 1.25)
    assert read_look(f'{{"photoGap": {huge}}}').photo_gap == 8


def test_dials_are_stored_as_round_numbers() -> None:
    sheet = look_sheet(parse_look({"accentHue": 71.6, "corners": 3.2, "textScale": 1.1234}))
    assert (sheet["accentHue"], sheet["corners"], sheet["textScale"]) == (72, 3, 1.12)


@pytest.mark.parametrize("field", ["accentHue", "corners", "photoGap"])
def test_a_dial_left_to_the_theme_stays_null(field: str) -> None:
    assert look_sheet(parse_look({field: None}))[field] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accentHue", "amber"),
        ("corners", True),  # a bool is a number to Python, not to the sheet
        ("photoGap", [2]),
        ("textScale", None),  # this dial has no "theme default"
        ("textScale", "1.1"),
        ("textScale", math.nan),
        ("accentHue", math.inf),
        ("showToday", "yes"),
        ("dockLabels", 1),
        ("theme", 3),
        ("collectionsRows", "people"),
    ],
)
def test_a_value_of_the_wrong_kind_is_rejected(field: str, value: object) -> None:
    with pytest.raises(LookError, match=f"'{field}'"):
        parse_look({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [("theme", "neon"), ("mode", "sepia"), ("thumbSize", "huge"), ("startPage", "admin")],
)
def test_an_unknown_choice_is_rejected(field: str, value: str) -> None:
    with pytest.raises(LookError, match=f"'{field}'"):
        parse_look({field: value})


def test_collections_rows_keep_their_order_and_refuse_repeats_strangers_and_none() -> None:
    assert look_sheet(parse_look({"collectionsRows": ["albums", "people"]}))["collectionsRows"] == [
        "albums",
        "people",
    ]
    for bad in (["people", "people"], ["people", "calendar"], [], [1]):
        with pytest.raises(LookError, match="'collectionsRows'"):
            parse_look({"collectionsRows": bad})


def test_hiding_today_starts_on_the_library() -> None:
    hidden = parse_look({"showToday": False, "startPage": "today"})
    assert (hidden.show_today, hidden.start_page) == (False, StartPage.LIBRARY)
    assert parse_look({"showToday": False}).start_page is StartPage.LIBRARY


@pytest.mark.parametrize("raw", [None, [], "dark", 3, [{"mode": "dark"}]])
def test_a_sheet_that_is_not_an_object_is_rejected(raw: object) -> None:
    with pytest.raises(LookError):
        parse_look(raw)


def test_a_stored_sheet_reads_back_as_it_was_written() -> None:
    look = parse_look(EVERYTHING)
    assert read_look(dump_look(look)) == look
    assert json.loads(dump_look(look)) == EVERYTHING


def test_nothing_stored_reads_as_the_defaults() -> None:
    assert read_look(None) == DEFAULT_LOOK


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "{not json",
        "[]",
        "null",
        '{"mode": "light", "css": "x"}',
        '{"textScale": "big"}',
        '{"theme": "gone-in-a-later-version"}',
    ],
)
def test_a_broken_stored_sheet_reads_as_the_defaults(stored: str) -> None:
    assert read_look(stored) == DEFAULT_LOOK
