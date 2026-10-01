from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.search_query import FACETS, ParsedQuery, parse_query


def test_plain_text_has_no_facets() -> None:
    assert parse_query("  kids in   the snow ") == ParsedQuery("kids in the snow", ())


def test_facets_are_split_from_free_text() -> None:
    parsed = parse_query("person:Lea beach at sunset place:France year:2023")
    assert parsed.text == "beach at sunset"
    assert parsed.values("person") == ["Lea"]
    assert parsed.values("place") == ["France"]
    assert parsed.values("date") == ["2023"]  # year: is an alias of date:


def test_quoted_values_and_repeated_facets() -> None:
    parsed = parse_query('person:"Lea Martin" person:Tom tag:snow')
    assert parsed.values("person") == ["Lea Martin", "Tom"]
    assert parsed.values("tag") == ["snow"]
    assert parsed.text == ""


def test_facet_names_are_case_insensitive_but_values_keep_case() -> None:
    assert parse_query("Person:Lea").values("person") == ["Lea"]


def test_unknown_prefixes_and_empty_values_stay_in_the_text() -> None:
    parsed = parse_query("dinner at 19:30 foo:bar person:")
    assert parsed.text == "dinner at 19:30 foo:bar person:"
    assert parsed.facets == ()


def test_dates_must_look_like_dates() -> None:
    assert parse_query("date:2023-07").values("date") == ["2023-07"]
    assert parse_query("date:2023-07-14").values("date") == ["2023-07-14"]
    assert parse_query("date:yesterday").text == "date:yesterday"


def test_unbalanced_quote_is_treated_as_text() -> None:
    assert parse_query('person:"Lea').text == 'person:"Lea'


def test_known_facets() -> None:
    assert {"date", "person", "place", "tag", "camera"} <= set(FACETS)


@given(st.text(max_size=80))
def test_parsing_never_crashes_and_text_has_no_double_spaces(q: str) -> None:
    parsed = parse_query(q)
    assert "  " not in parsed.text
    assert parsed.text == parsed.text.strip()


def test_date_place_and_camera_facets_become_library_filters() -> None:
    from datetime import date

    from photo_assistant.domain.library_filter import AssetFilter
    from photo_assistant.domain.search_query import with_facets

    base = AssetFilter(favourite=True)
    assert with_facets(base, parse_query("date:2019")) == AssetFilter(favourite=True, year=2019)
    assert with_facets(base, parse_query("date:2019-07")) == AssetFilter(
        favourite=True, year=2019, month=7
    )
    day = with_facets(base, parse_query('date:2021-01-02 place:"Le Havre" camera:X100'))
    assert day == AssetFilter(
        favourite=True,
        from_day=date(2021, 1, 2),
        to_day=date(2021, 1, 2),
        place="Le Havre",
        camera="X100",
    )
    # person and tag facets are not SQL filters: left for the ML store
    assert with_facets(base, parse_query("person:Lea tag:beach")) == base


def test_an_impossible_date_facet_is_an_error() -> None:
    import pytest

    from photo_assistant.domain.library_filter import AssetFilter
    from photo_assistant.domain.search_query import InvalidFacetError, with_facets

    with pytest.raises(InvalidFacetError):
        with_facets(AssetFilter(), parse_query("date:2021-13"))
    with pytest.raises(InvalidFacetError):
        with_facets(AssetFilter(), parse_query("date:2021-02-30"))
