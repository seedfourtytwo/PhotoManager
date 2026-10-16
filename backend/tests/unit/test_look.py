"""The look sheet's rules (spec 2026-10-08 §5, docs/adr/0001): unknown fields rejected,
numbers clamped, a stored sheet loses only the fields that no longer pass."""

import json
import math
from pathlib import Path

import pytest

from photo_assistant.domain.look import (
    DEFAULT_LOOK,
    CollectionsRow,
    Face,
    HomeSection,
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
    with_sent,
)

# The table both sides run (web/src/lib/look/sheet.spec.ts reads the same file).
CASES = json.loads(
    (Path(__file__).parents[3] / "docs" / "contracts" / "look-cases.json").read_text()
)


def _case_id(case: dict[str, object]) -> str:
    return json.dumps(case["sheet"])[:40]


EVERYTHING = {
    "theme": "album",
    "mode": "light",
    "accentHue": 200,
    "corners": 4,
    "photoGap": 6,
    "textScale": 1.15,
    "face": "atkinson",
    "thumbSize": "large",
    "showToday": True,
    "startPage": "library",
    "collectionsRows": ["albums", "people"],
    "dockLabels": False,
    "homeSections": ["people", "pinned"],
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
        "face": "inter",
        "thumbSize": "medium",
        "showToday": True,
        "startPage": "today",
        "collectionsRows": ["people", "places", "albums"],
        "dockLabels": True,
        "homeSections": [
            "on_this_day",
            "rediscover",
            "memories",
            "suggested",
            "years",
            "pinned",
            "people",
            "new",
        ],
    }


def test_every_field_is_read() -> None:
    assert parse_look(EVERYTHING) == Look(
        theme=Theme.ALBUM,
        mode=Mode.LIGHT,
        accent_hue=200,
        corners=4,
        photo_gap=6,
        text_scale=1.15,
        face=Face.ATKINSON,
        thumb_size=ThumbSize.LARGE,
        show_today=True,
        start_page=StartPage.LIBRARY,
        collections_rows=(CollectionsRow.ALBUMS, CollectionsRow.PEOPLE),
        dock_labels=False,
        home_sections=(HomeSection.PEOPLE, HomeSection.PINNED),
    )
    assert look_sheet(parse_look(EVERYTHING)) == EVERYTHING


def test_the_face_is_inter_or_the_larger_text_face_and_nothing_else() -> None:
    assert parse_look({}).face is Face.INTER
    assert parse_look({"face": "atkinson"}).face is Face.ATKINSON
    with pytest.raises(LookError, match="'face' must be one of: inter, atkinson"):
        parse_look({"face": "comic-sans"})
    assert read_look(json.dumps({"face": "gone", "mode": "light"})) == Look(mode=Mode.LIGHT)


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


def test_a_number_beyond_every_float_is_clamped_too() -> None:
    sheet = look_sheet(parse_look({"accentHue": math.inf, "textScale": -math.inf}))
    assert (sheet["accentHue"], sheet["textScale"]) == (360, 0.9)


@pytest.mark.parametrize("case", CASES["sent"], ids=_case_id)
def test_a_sent_sheet_reads_as_the_shared_table_says(case: dict[str, object]) -> None:
    gives = case["gives"]
    assert isinstance(gives, dict)
    assert look_sheet(parse_look(case["sheet"])) == {**look_sheet(DEFAULT_LOOK), **gives}


def test_a_half_rounds_up_not_to_the_even_number() -> None:
    sheet = look_sheet(parse_look({"accentHue": 0.5, "corners": 2.5, "textScale": 1.125}))
    assert (sheet["accentHue"], sheet["corners"], sheet["textScale"]) == (1, 3, 1.13)
    assert type(sheet["accentHue"]) is int


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
        ("accentHue", math.nan),
        ("showToday", "yes"),
        ("dockLabels", 1),
        ("theme", 3),
        ("collectionsRows", "people"),
        ("homeSections", "people"),
    ],
)
def test_a_value_of_the_wrong_kind_is_rejected(field: str, value: object) -> None:
    with pytest.raises(LookError, match=f"'{field}'"):
        parse_look({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("theme", "neon"),
        ("mode", "sepia"),
        ("thumbSize", "huge"),
        ("face", "comic"),
        ("startPage", "admin"),
    ],
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


def test_home_sections_keep_their_order_and_refuse_repeats_strangers_and_none() -> None:
    sent = parse_look({"homeSections": ["pinned", "on_this_day"]})
    assert look_sheet(sent)["homeSections"] == ["pinned", "on_this_day"]
    for bad in (["pinned", "pinned"], ["pinned", "weather"], [], [1]):
        with pytest.raises(LookError, match="'homeSections'"):
            parse_look({"homeSections": bad})


def test_what_an_account_sends_lies_over_its_look() -> None:
    warm = parse_look({"theme": "album", "accentHue": 30, "showToday": False})
    mine = with_sent(warm, {"homeSections": ["years"], "mode": "light"})
    assert mine == Look(
        theme=Theme.ALBUM,
        mode=Mode.LIGHT,
        accent_hue=30,
        show_today=False,
        start_page=StartPage.LIBRARY,
        home_sections=(HomeSection.YEARS,),
    )
    with pytest.raises(LookError, match="'homeSections'"):
        with_sent(warm, {"homeSections": []})


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
        '{"css": "x"}',
        '{"textScale": "big"}',
        '{"theme": "gone-in-a-later-version"}',
    ],
)
def test_a_broken_stored_sheet_reads_as_the_defaults(stored: str) -> None:
    assert read_look(stored) == DEFAULT_LOOK


@pytest.mark.parametrize("case", CASES["stored"], ids=_case_id)
def test_a_stored_sheet_reads_as_the_shared_table_says(case: dict[str, object]) -> None:
    reads = case["reads"]
    assert isinstance(reads, dict)
    stored = json.dumps(case["sheet"])
    assert look_sheet(read_look(stored)) == {**look_sheet(DEFAULT_LOOK), **reads}


def test_a_stored_sheet_loses_only_the_fields_that_no_longer_pass() -> None:
    stored = '{"theme": "gone-in-a-later-version", "mode": "light", "accentHue": 200, "css": "x"}'
    assert read_look(stored) == Look(mode=Mode.LIGHT, accent_hue=200)


def test_a_sent_sheet_with_one_bad_field_is_still_refused_whole() -> None:
    with pytest.raises(LookError, match="'theme'"):
        parse_look({"theme": "gone-in-a-later-version", "accentHue": 200})
