"""Edit recipes: validation and the size maths shared by preview, thumbnails and export."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.edit_recipe import (
    Crop,
    InvalidRecipeError,
    Recipe,
    edited_size,
    fit_within,
    straighten_scale,
)


def test_the_default_recipe_changes_nothing() -> None:
    assert Recipe().is_identity
    assert edited_size(4000, 3000, Recipe()) == (4000, 3000)
    assert not Recipe(rotate=90).is_identity


@pytest.mark.parametrize(
    "bad",
    [
        {"rotate": 45},
        {"straighten": 15.5},
        {"straighten": -16},
        {"crop": {"x": -0.1, "y": 0, "w": 0.5, "h": 0.5}},
        {"crop": {"x": 0.6, "y": 0, "w": 0.5, "h": 0.5}},
        {"crop": {"x": 0, "y": 0, "w": 0, "h": 0.5}},
        {"crop": {"x": 0, "y": 0, "w": 0.5}},
        {"crop": {"x": 0, "y": 0, "w": 1e-12, "h": 0.5}},  # QA A6: 500s and broken ZIPs
        {"crop": {"x": 0, "y": 0, "w": 0.5, "h": 0.0009}},
        {"flip_horizontal": "yes"},
        {"straighten": float("nan")},
    ],
)
def test_invalid_recipes_are_refused_with_a_reason(bad: dict[str, object]) -> None:
    with pytest.raises(InvalidRecipeError):
        Recipe.from_dict(bad)


def test_round_trip_through_json_data() -> None:
    recipe = Recipe(rotate=270, flip_vertical=True, crop=Crop(0.1, 0.2, 0.5, 0.25), straighten=-3)
    assert Recipe.from_dict(recipe.to_dict()) == recipe
    assert recipe.to_dict()["crop"] == {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.25}
    assert Recipe.from_dict({}) == Recipe()


def test_the_key_identifies_the_recipe() -> None:
    a = Recipe(rotate=90)
    assert a.key == Recipe(rotate=90).key
    assert a.key != Recipe(rotate=180).key
    assert len(a.key) == 16


def test_quarter_turns_swap_width_and_height() -> None:
    assert edited_size(4000, 3000, Recipe(rotate=90)) == (3000, 4000)
    assert edited_size(4000, 3000, Recipe(rotate=180, flip_horizontal=True)) == (4000, 3000)


def test_crop_is_a_fraction_of_the_rotated_image() -> None:
    recipe = Recipe(rotate=90, crop=Crop(0, 0, 0.5, 0.25))
    assert edited_size(4000, 3000, recipe) == (1500, 1000)


def test_straightening_keeps_the_aspect_ratio_without_empty_corners() -> None:
    assert straighten_scale(4000, 3000, 0) == 1
    scale = straighten_scale(4000, 3000, 10)
    theta = math.radians(10)
    # the inner rectangle's corner stays inside the rotated frame
    assert 4000 * scale * math.cos(theta) + 3000 * scale * math.sin(theta) <= 4000 + 1e-6
    w, h = edited_size(4000, 3000, Recipe(straighten=10))
    assert abs(w / h - 4 / 3) < 0.01 and w < 4000


@given(
    w=st.integers(1, 10000),
    h=st.integers(1, 10000),
    deg=st.floats(-15, 15),
)
def test_straighten_scale_is_between_zero_and_one(w: int, h: int, deg: float) -> None:
    assert 0 < straighten_scale(w, h, deg) <= 1


def test_fit_within_never_upscales() -> None:
    assert fit_within(4000, 3000, 2048) == (2048, 1536)
    assert fit_within(1000, 800, 2048) == (1000, 800)
    assert fit_within(3000, 4000, None) == (3000, 4000)
    assert fit_within(10000, 1, 100) == (100, 1)


def test_the_smallest_crop_is_a_thousandth_of_the_photo() -> None:
    from photo_assistant.domain.edit_recipe import MIN_CROP

    assert MIN_CROP == 0.001
    Crop(0.999, 0.999, 0.001, 0.001)  # allowed: the renderer keeps at least one pixel


def test_download_options_refuse_an_absurd_max_edge() -> None:
    from photo_assistant.domain.export_naming import MAX_EDGE, ExportOptions, OptionsError

    assert ExportOptions(max_edge=MAX_EDGE).max_edge == 20000
    with pytest.raises(OptionsError, match="20000"):
        ExportOptions(max_edge=MAX_EDGE + 1)
