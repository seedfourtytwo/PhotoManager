from datetime import date

import pytest

from photo_assistant.domain.library_filter import (
    AssetFilter,
    filter_problem,
    like_pattern,
    search_terms,
)
from photo_assistant.domain.places import Place


def test_an_empty_filter_is_fine() -> None:
    assert filter_problem(AssetFilter()) is None


@pytest.mark.parametrize(
    ("f", "message"),
    [
        (AssetFilter(month=7), "month needs a year"),
        (AssetFilter(year=2019, month=13), "month"),
        (AssetFilter(year=0), "year"),
        (AssetFilter(from_day=date(2020, 1, 2), to_day=date(2020, 1, 1)), "before"),
        (AssetFilter(q="x" * 201), "too long"),
        (AssetFilter(source_ids=(0,)), "no such source"),
        (AssetFilter(person_ids=(0,)), "no such person"),
        (AssetFilter(person_ids=(2**63,)), "no such person"),
    ],
)
def test_contradictions_are_explained(f: AssetFilter, message: str) -> None:
    problem = filter_problem(f)
    assert problem is not None and message in problem


def test_search_text_splits_into_at_most_eight_terms() -> None:
    assert search_terms("  beach   Brittany ") == ["beach", "Brittany"]
    assert search_terms(None) == []
    assert len(search_terms(" ".join(str(i) for i in range(20)))) == 8


def test_like_patterns_escape_wildcards() -> None:
    assert like_pattern("50%_off\\") == "%50\\%\\_off\\\\%"


def test_place_label_skips_missing_parts() -> None:
    assert Place("France", "Brittany", "Quimper").label == "Quimper, Brittany, France"
    assert Place("France", "", "").label == "France"
