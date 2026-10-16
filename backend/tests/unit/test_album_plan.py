"""AlbumPlan is only ever a proposal: parse the LLM's JSON strictly, then validate it."""

import pytest

from photo_assistant.domain.album_plan import (
    AlbumPlan,
    AssetSummary,
    LibrarySummary,
    PlanFormatError,
    PlanSection,
    plan_from_json,
    plan_to_json,
    summary_lines,
    validate,
)

LAYOUTS = {"full": 1, "grid-2": 2, "text": 0}  # photos per page


def _plan(*sections: PlanSection, title: str = "Summer 2019") -> AlbumPlan:
    return AlbumPlan(title=title, sections=tuple(sections))


def _section(ids: tuple[int, ...] = (1, 2), **kw: object) -> PlanSection:
    return PlanSection(
        title=str(kw.get("title", "Beach")),
        asset_ids=ids,
        layout_hint=str(kw.get("layout_hint", "grid-2")),
        captions=kw.get("captions", {}),  # type: ignore[arg-type]
    )


def test_a_good_plan_has_no_problems() -> None:
    plan = _plan(_section((1, 2), captions={1: "Waves"}), _section((3,), layout_hint="full"))
    assert validate(plan, {1, 2, 3}, LAYOUTS) == []


def test_every_photo_of_the_event_must_be_used() -> None:
    # The benchmark: models left photos out when nothing said they may not
    problems = validate(_plan(_section((1, 2))), {1, 2, 3, 4}, LAYOUTS)
    assert problems == ["not used: photo 3, 4; put every photo in exactly one section"]


def test_a_layout_must_fill_whole_pages_of_its_section() -> None:
    plan = _plan(_section((1, 2, 3)), _section((4, 5), layout_hint="full"))
    assert validate(plan, {1, 2, 3, 4, 5}, LAYOUTS) == [
        "section 1 ('Beach'): layout 'grid-2' holds 2 photos a page, but the section has 3"
    ]


def test_a_text_layout_cannot_hold_photos() -> None:
    problems = validate(_plan(_section((1,), layout_hint="text")), {1}, LAYOUTS)
    assert problems == ["section 1 ('Beach'): layout 'text' holds no photos"]


def test_unknown_asset_ids_are_reported() -> None:
    problems = validate(
        _plan(_section((1, 99)), _section((2,), layout_hint="full")), {1, 2}, LAYOUTS
    )
    assert problems == ["section 1 ('Beach'): unknown photo id 99"]


def test_a_photo_used_twice_is_reported() -> None:
    problems = validate(
        _plan(_section((1, 2)), _section((2,), title="Town", layout_hint="full")), {1, 2}, LAYOUTS
    )
    assert problems == ["section 2 ('Town'): photo 2 is used more than once"]


def test_empty_sections_and_empty_plans_are_reported() -> None:
    assert validate(_plan(_section(()), _section((1,), layout_hint="full")), {1}, LAYOUTS) == [
        "section 1 ('Beach'): has no photos"
    ]
    assert validate(_plan(), set(), LAYOUTS) == ["the plan has no sections"]


def test_unknown_layout_is_reported() -> None:
    problems = validate(_plan(_section((1,), layout_hint="collage")), {1}, LAYOUTS)
    assert problems == ["section 1 ('Beach'): unknown layout 'collage'"]


def test_over_long_or_misplaced_captions_are_reported() -> None:
    plan = _plan(_section((1, 3), captions={1: "x" * 201, 2: "elsewhere"}), _section((2, 4)))
    assert validate(plan, {1, 2, 3, 4}, LAYOUTS, max_caption_chars=200) == [
        "section 1 ('Beach'): caption for photo 1 is longer than 200 characters",
        "section 1 ('Beach'): caption for photo 2, which is not in this section",
    ]


def test_blank_titles_are_reported() -> None:
    plan = _plan(_section((1,), title=" ", layout_hint="full"), title="")
    assert validate(plan, {1}, LAYOUTS) == [
        "the plan has no title",
        "section 1 (''): has no title",
    ]


WIRE = {
    "title": "Summer",
    "sections": [
        {
            "title": "Beach",
            "asset_ids": [1, 2],
            "layout_hint": "grid-4",
            "captions": [{"asset_id": 1, "text": "Waves"}],
        }
    ],
}


def test_plan_from_json_reads_the_wire_shape() -> None:
    plan = plan_from_json(WIRE)
    assert plan == AlbumPlan("Summer", (PlanSection("Beach", (1, 2), "grid-4", {1: "Waves"}),))


def test_plan_to_json_writes_the_wire_shape_back() -> None:
    assert plan_to_json(plan_from_json(WIRE)) == WIRE


def test_captions_are_optional_on_the_wire() -> None:
    wire = {"title": "T", "sections": [{"title": "S", "asset_ids": [1], "layout_hint": "full"}]}
    assert plan_from_json(wire).sections[0].captions == {}


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"title": 1, "sections": []},
        {"title": "T"},
        {"title": "T", "sections": {}},
        {"title": "T", "sections": [1]},
        {"title": "T", "sections": [{"title": "S", "asset_ids": ["1"], "layout_hint": "x"}]},
        {"title": "T", "sections": [{"title": "S", "asset_ids": [True], "layout_hint": "x"}]},
        {"title": "T", "sections": [{"title": "S", "asset_ids": 1, "layout_hint": "x"}]},
        {"title": "T", "sections": [{"asset_ids": [1], "layout_hint": "x"}]},
        {
            "title": "T",
            "sections": [
                {"title": "S", "asset_ids": [1], "layout_hint": "x", "captions": [{"text": 1}]}
            ],
        },
        {
            "title": "T",
            "sections": [{"title": "S", "asset_ids": [1], "layout_hint": "x", "captions": 3}],
        },
    ],
)
def test_plan_from_json_rejects_malformed_shapes(bad: object) -> None:
    with pytest.raises(PlanFormatError):
        plan_from_json(bad)


def test_library_summary_is_compact_and_lists_ids() -> None:
    summary = LibrarySummary(
        assets=(
            AssetSummary(7, "2019-07-04", "Lyon, France", ("beach", "sea")),
            AssetSummary(8, "2019-07-05", None),
            AssetSummary(9, "2019-07-05", caption="Two kids | one kite.\nWindy."),
        ),
        layouts={"full": 1},
    )
    assert summary.asset_ids == frozenset({7, 8, 9})
    assert summary_lines(summary) == (
        "7|2019-07-04|Lyon, France|beach,sea|\n"
        "8|2019-07-05|||\n"
        "9|2019-07-05|||Two kids / one kite. Windy."
    )
