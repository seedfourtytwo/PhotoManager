"""AlbumPlan is only ever a proposal: parse the LLM's JSON strictly, then validate it."""

import pytest

from photo_assistant.domain.album_plan import (
    AlbumPlan,
    AssetSummary,
    LibrarySummary,
    PlanFormatError,
    PlanSection,
    plan_from_json,
    summary_lines,
    validate,
)

LAYOUTS = {"full", "grid-4"}


def _plan(*sections: PlanSection, title: str = "Summer 2019") -> AlbumPlan:
    return AlbumPlan(title=title, sections=tuple(sections))


def _section(ids: tuple[int, ...] = (1, 2), **kw: object) -> PlanSection:
    return PlanSection(
        title=str(kw.get("title", "Beach")),
        asset_ids=ids,
        layout_hint=str(kw.get("layout_hint", "grid-4")),
        captions=kw.get("captions", {}),  # type: ignore[arg-type]
    )


def test_a_good_plan_has_no_problems() -> None:
    plan = _plan(_section((1, 2), captions={1: "Waves"}), _section((3,), layout_hint="full"))
    assert validate(plan, {1, 2, 3}, LAYOUTS) == []


def test_unknown_asset_ids_are_reported() -> None:
    problems = validate(_plan(_section((1, 99))), {1, 2}, LAYOUTS)
    assert problems == ["section 1 ('Beach'): unknown photo id 99"]


def test_a_photo_used_twice_is_reported() -> None:
    problems = validate(_plan(_section((1, 2)), _section((2,), title="Town")), {1, 2}, LAYOUTS)
    assert problems == ["section 2 ('Town'): photo 2 is used more than once"]


def test_empty_sections_and_empty_plans_are_reported() -> None:
    assert validate(_plan(_section(())), {1}, LAYOUTS) == ["section 1 ('Beach'): has no photos"]
    assert validate(_plan(), {1}, LAYOUTS) == ["the plan has no sections"]


def test_unknown_layout_is_reported() -> None:
    problems = validate(_plan(_section((1,), layout_hint="collage")), {1}, LAYOUTS)
    assert problems == ["section 1 ('Beach'): unknown layout 'collage'"]


def test_over_long_or_misplaced_captions_are_reported() -> None:
    plan = _plan(_section((1,), captions={1: "x" * 201, 2: "elsewhere"}))
    assert validate(plan, {1, 2}, LAYOUTS, max_caption_chars=200) == [
        "section 1 ('Beach'): caption for photo 1 is longer than 200 characters",
        "section 1 ('Beach'): caption for photo 2, which is not in this section",
    ]


def test_blank_titles_are_reported() -> None:
    plan = _plan(_section((1,), title=" "), title="")
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
        ),
        layouts=("full",),
    )
    assert summary.asset_ids == frozenset({7, 8})
    assert summary_lines(summary) == "7|2019-07-04|Lyon, France|beach,sea\n8|2019-07-05||"
