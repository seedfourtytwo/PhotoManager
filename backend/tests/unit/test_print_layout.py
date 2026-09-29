"""Print layout rules (FEATURES §5.4, §6): trim sizes, templates, crop math, auto layout."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from photo_assistant.domain.print_layout import (
    BLEED_MM,
    COVER_LAYOUT,
    LAYOUTS,
    SAFE_MARGIN_MM,
    TEXT_LAYOUT_ID,
    TRIM_SIZES,
    Fit,
    Page,
    PageGeometry,
    Rect,
    Resolution,
    UnknownLayoutError,
    UnknownTrimSizeError,
    auto_layout,
    check_resolution,
    contain_frame,
    cover_crop,
    effective_ppi,
    layout,
    place_photo,
    trim_size,
)

A4_LANDSCAPE = TRIM_SIZES["a4-landscape"]
A4_PORTRAIT = TRIM_SIZES["a4-portrait"]
LANDSCAPE = 3 / 2
PORTRAIT = 3 / 4


def geometry(trim_id: str = "a4-landscape", margin: float = 18.0) -> PageGeometry:
    return PageGeometry(trim_size(trim_id), margin_mm=margin, gutter_mm=4.0, caption_band_mm=10.0)


# --- trim sizes --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trim_id", "width", "height"),
    [
        ("a4-portrait", 210, 297),
        ("a4-landscape", 297, 210),
        ("a5-portrait", 148, 210),
        ("a5-landscape", 210, 148),
        ("square-20", 200, 200),
        ("us-letter", 215.9, 279.4),
    ],
)
def test_trim_presets_in_mm(trim_id: str, width: float, height: float) -> None:
    trim = trim_size(trim_id)
    assert (trim.width_mm, trim.height_mm) == (width, height)
    assert trim.aspect == pytest.approx(width / height)


def test_unknown_trim_size_is_a_typed_error() -> None:
    with pytest.raises(UnknownTrimSizeError, match="b5"):
        trim_size("b5")


def test_bleed_and_safe_margin_constants() -> None:
    assert (BLEED_MM, SAFE_MARGIN_MM) == (3.0, 5.0)


# --- layouts as data ---------------------------------------------------------------------------


def test_curated_layout_set() -> None:
    assert set(LAYOUTS) == {
        "full-bleed",
        "single",
        "two-side",
        "two-stacked",
        "three-grid",
        "hero-two",
        "hero-two-side",
        "four-grid",
        TEXT_LAYOUT_ID,
    }
    assert layout(TEXT_LAYOUT_ID).slots == ()
    assert layout("four-grid").capacity == 4
    assert layout("full-bleed").bleed
    assert layout("single").fit is Fit.CONTAIN


def test_unknown_layout_is_a_typed_error() -> None:
    with pytest.raises(UnknownLayoutError):
        layout("collage-17")


@pytest.mark.parametrize("layout_id", [k for k in LAYOUTS if k != TEXT_LAYOUT_ID])
def test_slots_are_unit_fractions_that_do_not_overlap(layout_id: str) -> None:
    slots = LAYOUTS[layout_id].slots
    for s in slots:
        assert 0 <= s.x and 0 <= s.y and s.right <= 1 + 1e-9 and s.bottom <= 1 + 1e-9
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            assert not a.overlaps(b)


def test_content_area_sits_inside_the_margins() -> None:
    g = geometry()
    assert g.content == Rect(18, 18, 297 - 36, 210 - 36)
    assert g.photo_area == Rect(18, 18, 297 - 36, 210 - 36 - 10)


def test_margin_is_never_below_the_safe_margin() -> None:
    g = PageGeometry(A4_PORTRAIT, margin_mm=2.0, gutter_mm=4.0, caption_band_mm=10.0)
    assert g.content.x == SAFE_MARGIN_MM


def test_slot_frames_get_a_gutter_only_between_photos() -> None:
    g = geometry()
    left, right = g.slot_frames(layout("two-side"))
    area = g.photo_area
    assert left.x == area.x and right.right == pytest.approx(area.right)
    assert right.x - left.right == pytest.approx(4.0)
    assert left.h == area.h


def test_full_bleed_frame_reaches_the_bleed_edge() -> None:
    (frame,) = geometry().slot_frames(layout("full-bleed"))
    assert frame == Rect(-3, -3, 303, 216)


@pytest.mark.parametrize("layout_id", [k for k in LAYOUTS if not LAYOUTS[k].bleed])
@pytest.mark.parametrize("trim_id", sorted(TRIM_SIZES))
def test_nothing_important_within_the_safe_margin(layout_id: str, trim_id: str) -> None:
    g = geometry(trim_id)
    trim = g.trim
    for f in g.slot_frames(layout(layout_id)):
        assert f.x >= SAFE_MARGIN_MM and f.y >= SAFE_MARGIN_MM
        assert f.right <= trim.width_mm - SAFE_MARGIN_MM
        assert f.bottom <= trim.height_mm - SAFE_MARGIN_MM


def test_caption_baseline_is_the_same_on_every_page_and_inside_the_band() -> None:
    g = geometry()
    assert g.photo_area.bottom < g.caption_baseline_mm <= g.content.bottom


def test_text_block_and_cover_title_sit_in_the_content_area() -> None:
    g = geometry()
    block = g.text_block
    assert g.content.x < block.x and block.right < g.content.right
    assert g.content.y < g.cover_title_baseline_mm < g.content.bottom
    (cover,) = g.slot_frames(COVER_LAYOUT)
    assert cover.bottom < g.cover_title_baseline_mm


# --- crop math ---------------------------------------------------------------------------------


def test_cover_crop_of_same_aspect_is_the_whole_image() -> None:
    assert cover_crop(1.5, 1.5) == Rect(0, 0, 1, 1)


def test_cover_crop_trims_the_long_side_around_the_focal_point() -> None:
    crop = cover_crop(2.0, 1.0)
    assert crop == Rect(0.25, 0, 0.5, 1)
    assert cover_crop(2.0, 1.0, focal=(0.0, 0.5)).x == 0
    assert cover_crop(2.0, 1.0, focal=(1.0, 0.5)).right == pytest.approx(1)
    tall = cover_crop(0.5, 1.0, focal=(0.5, 0.1))
    assert (tall.x, tall.w, tall.h) == (0, 1, 0.5) and tall.y == 0


aspects = st.floats(min_value=0.2, max_value=5.0)
unit = st.floats(min_value=0.0, max_value=1.0)


@given(aspects, aspects, unit, unit)
def test_cover_crop_keeps_frame_aspect_and_stays_inside(
    image: float, frame: float, fx: float, fy: float
) -> None:
    crop = cover_crop(image, frame, focal=(fx, fy))
    assert 0 <= crop.x and 0 <= crop.y
    assert crop.right <= 1 + 1e-9 and crop.bottom <= 1 + 1e-9
    assert max(crop.w, crop.h) == pytest.approx(1)
    assert (crop.w * image) / crop.h == pytest.approx(frame, rel=1e-6)


def test_contain_frame_centres_the_photo_in_its_slot() -> None:
    slot = Rect(0, 0, 200, 100)
    assert contain_frame(1.0, slot) == Rect(50, 0, 100, 100)
    assert contain_frame(4.0, slot) == Rect(0, 25, 200, 50)


def test_place_photo_uses_the_layout_fit() -> None:
    slot = Rect(10, 10, 100, 100)
    contained = place_photo(layout("single"), slot, 2.0)
    assert contained.crop == Rect(0, 0, 1, 1)
    assert contained.frame == Rect(10, 35, 100, 50)
    covered = place_photo(layout("four-grid"), slot, 2.0, focal=(0.5, 0.5))
    assert covered.frame == slot
    assert covered.crop == Rect(0.25, 0, 0.5, 1)


# --- resolution --------------------------------------------------------------------------------


def test_effective_ppi_uses_the_cropped_pixels() -> None:
    # 3000 px across 254 mm (10 in) = 300 ppi; cropping half the width halves it.
    frame = Rect(0, 0, 254, 254)
    assert effective_ppi(3000, 3000, Rect(0, 0, 1, 1), frame) == pytest.approx(300)
    assert effective_ppi(3000, 3000, Rect(0, 0, 0.5, 1), frame) == pytest.approx(150)


@pytest.mark.parametrize(
    ("ppi", "expected"),
    [
        (300, Resolution.OK),
        (200, Resolution.OK),
        (199.9, Resolution.WARN),
        (150, Resolution.WARN),
        (149.9, Resolution.BLOCK),
    ],
)
def test_resolution_thresholds(ppi: float, expected: Resolution) -> None:
    assert check_resolution(ppi) is expected


# --- auto layout -------------------------------------------------------------------------------


def photo_indices(pages: list[Page]) -> list[int]:
    return [i for page in pages for i in page.photos]


def test_no_photos_no_pages() -> None:
    assert auto_layout([], geometry()) == []


def test_two_portraits_on_a_landscape_page_sit_side_by_side() -> None:
    (page,) = auto_layout([PORTRAIT, PORTRAIT], geometry("a4-landscape"))
    assert page == Page("two-side", (0, 1))


def test_two_landscapes_on_a_portrait_page_are_stacked() -> None:
    (page,) = auto_layout([LANDSCAPE, LANDSCAPE], geometry("a4-portrait"))
    assert page == Page("two-stacked", (0, 1))


def test_a_panorama_is_not_squeezed_into_a_grid() -> None:
    pages = auto_layout([PORTRAIT, PORTRAIT, 4.0, PORTRAIT, PORTRAIT], geometry("a4-landscape"))
    (pano_page,) = [p for p in pages if 2 in p.photos]
    assert pano_page.photos == (2,)


def test_a_long_run_of_similar_photos_varies_the_rhythm() -> None:
    pages = auto_layout([LANDSCAPE] * 24, geometry("a4-landscape"))
    ids = [p.layout_id for p in pages]
    assert len(set(ids)) >= 2
    assert all(a != b for a, b in zip(ids, ids[1:], strict=False))


def test_auto_layout_keeps_crops_small_for_ordinary_photos() -> None:
    g = geometry("a4-landscape")
    mixed = [LANDSCAPE, 4 / 3, PORTRAIT, PORTRAIT, LANDSCAPE, 1.0, 4 / 3, 2 / 3, LANDSCAPE]
    for page in auto_layout(mixed, g):
        frames = g.slot_frames(layout(page.layout_id))
        for index, frame in zip(page.photos, frames, strict=True):
            crop = place_photo(layout(page.layout_id), frame, mixed[index]).crop
            assert crop.w * crop.h > 0.6


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.floats(min_value=0.25, max_value=4.0), max_size=40),
    st.sampled_from(sorted(TRIM_SIZES)),
)
def test_every_photo_is_placed_exactly_once_in_order(photos: list[float], trim_id: str) -> None:
    pages = auto_layout(photos, geometry(trim_id))
    assert photo_indices(pages) == list(range(len(photos)))
    for page in pages:
        assert len(page.photos) == layout(page.layout_id).capacity
        assert page.layout_id != TEXT_LAYOUT_ID


def test_rect_helpers() -> None:
    r = Rect(1, 2, 3, 4)
    assert (r.right, r.bottom, r.aspect) == (4, 6, 0.75)
    assert r.inset(1) == Rect(2, 3, 1, 2)
    assert not r.overlaps(Rect(4, 2, 1, 1))
    assert math.isclose(Rect(0, 0, 2, 1).aspect, 2)
