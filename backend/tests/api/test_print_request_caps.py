"""A print request is bounded by what a book can hold: pages, photos a page, text length."""

from typing import Any

import pytest
from pydantic import ValidationError

from photo_assistant.api.routes.printing import (
    MAX_PAGE_TEXT,
    MAX_PAGES,
    PageIn,
    PrintRequestIn,
)
from photo_assistant.domain.print_layout import LAYOUTS

BIGGEST = max(lay.capacity for lay in LAYOUTS.values())
TEXT_PAGE = {"layout_id": "text", "asset_ids": [], "text": "Day 1"}


def test_the_largest_real_request_is_accepted() -> None:
    page = PageIn(layout_id="four-grid", asset_ids=list(range(1, BIGGEST + 1)), text="x")
    assert len(page.asset_ids) == BIGGEST
    assert PageIn(layout_id="text", asset_ids=[], text="x" * MAX_PAGE_TEXT).text
    assert len(PrintRequestIn(pages=[PageIn(**TEXT_PAGE)] * MAX_PAGES).pages or []) == MAX_PAGES


@pytest.mark.parametrize(
    "page",
    [
        {"layout_id": "four-grid", "asset_ids": list(range(1, BIGGEST + 2))},  # no layout so big
        {"layout_id": "single", "asset_ids": [10**30]},  # beyond SQLite's integers
        {"layout_id": "single", "asset_ids": [0]},
        {"layout_id": "text", "asset_ids": [], "text": "x" * (MAX_PAGE_TEXT + 1)},
        {"layout_id": "x" * 41, "asset_ids": []},
    ],
)
def test_a_page_beyond_what_a_layout_holds_is_refused(page: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PageIn(**page)


@pytest.mark.parametrize(
    "request_body",
    [
        {"pages": [TEXT_PAGE] * (MAX_PAGES + 1)},
        {"trim": "x" * 41},
        {"theme": "x" * 41},
    ],
)
def test_a_request_beyond_what_a_book_holds_is_refused(request_body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PrintRequestIn(**request_body)
