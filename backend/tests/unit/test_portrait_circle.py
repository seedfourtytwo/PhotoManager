"""A person's round portrait (issue 53): a circle on the photo as displayed, without edits.

Invariants, whatever the face box and the photo's shape: the square round the circle is
pixel-square, lies inside the photo, and is a crop the renderer accepts.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.edit_recipe import Crop
from photo_assistant.domain.faces import (
    BoundingBox,
    Circle,
    InvalidPortraitError,
    automatic_circle,
    circle_box,
    fit_circle,
    overlap,
    photo_size,
)

EPSILON = 1e-9
edges = st.integers(1, 12_000)
fractions = st.floats(0, 1)
anything_finite = st.floats(-1e6, 1e6)


@st.composite
def photos(draw: st.DrawFn) -> tuple[int, int]:
    """No stranger than 100:1; a crop keeps at least 1/1000 of each side."""
    width, height = draw(edges), draw(edges)
    short, long = min(width, height), max(width, height)
    return (width, height) if long <= 100 * short else (short, short)


@st.composite
def boxes(draw: st.DrawFn) -> BoundingBox:
    x, y = draw(fractions), draw(fractions)
    return BoundingBox(x, y, draw(st.floats(0, 1 - x)), draw(st.floats(0, 1 - y)))


def assert_a_square_inside(box: BoundingBox, width: int, height: int) -> None:
    assert box.x >= 0 and box.y >= 0
    assert box.x + box.width <= 1 + EPSILON and box.y + box.height <= 1 + EPSILON
    assert box.width * width == pytest.approx(box.height * height), "pixel-square"
    Crop(box.x, box.y, box.width, box.height)  # raises if the renderer would refuse it


# --- the automatic circle ---------------------------------------------------------------------


def test_the_automatic_circle_is_twice_the_face_with_more_room_above() -> None:
    # a 400 px face in the middle of a 4000 x 3000 photo
    face = BoundingBox(0.45, 0.4, 0.1, 400 / 3000)
    circle = automatic_circle(face, 4000, 3000)
    assert circle.size == pytest.approx(800 / 3000)
    assert circle.cx == pytest.approx(0.5)
    centre_of_face = 0.4 + 200 / 3000
    assert circle.cy < centre_of_face, "moved up, so the hair fits"
    box = circle_box(circle, 4000, 3000)
    assert box.y < face.y and box.y + box.height > face.y + face.height, "hair and chin"
    assert (box.width * 4000, box.height * 3000) == pytest.approx((800, 800))


def test_a_face_box_that_is_not_square_is_never_stretched() -> None:
    tall_face = BoundingBox(0.4, 0.3, 0.05, 0.3)  # 200 x 900 px
    box = circle_box(automatic_circle(tall_face, 4000, 3000), 4000, 3000)
    assert (box.width * 4000, box.height * 3000) == pytest.approx((1800, 1800))


@pytest.mark.parametrize(("width", "height"), [(4000, 3000), (3000, 4000), (1000, 1000)])
def test_a_face_filling_the_photo_gets_the_largest_square_that_fits(
    width: int, height: int
) -> None:
    circle = automatic_circle(BoundingBox(0.1, 0.1, 0.8, 0.8), width, height)
    assert circle.size == 1.0
    assert_a_square_inside(circle_box(circle, width, height), width, height)


def test_a_face_in_a_corner_keeps_its_circle_inside_the_photo() -> None:
    box = circle_box(automatic_circle(BoundingBox(0, 0, 0.1, 0.1), 3000, 4000), 3000, 4000)
    assert (box.x, box.y) == (0, 0)
    far = circle_box(automatic_circle(BoundingBox(0.9, 0.9, 0.1, 0.1), 3000, 4000), 3000, 4000)
    assert far.x + far.width == pytest.approx(1) and far.y + far.height == pytest.approx(1)


@given(box=boxes(), photo=photos())
def test_every_automatic_portrait_is_a_square_inside_the_photo(
    box: BoundingBox, photo: tuple[int, int]
) -> None:
    circle = automatic_circle(box, *photo)
    assert 0 < circle.size <= 1
    assert_a_square_inside(circle_box(circle, *photo), *photo)


# --- a circle someone chose -------------------------------------------------------------------


def test_a_circle_inside_the_photo_is_kept_as_it_is() -> None:
    circle = Circle(0.5, 0.4, 0.5)
    assert fit_circle(circle, 4000, 3000) == circle
    box = circle_box(circle, 4000, 3000)
    assert (box.x, box.y, box.width, box.height) == pytest.approx((0.3125, 0.15, 0.375, 0.5))


def test_out_of_range_numbers_are_brought_inside_not_refused() -> None:
    fitted = fit_circle(Circle(-5, 7, 3), 4000, 3000)
    assert (fitted.cx, fitted.cy, fitted.size) == pytest.approx((0.375, 0.5, 1.0)), "at the left"
    small = fit_circle(Circle(0.5, 0.5, -1), 4000, 3000)
    assert 0 < small.size < 0.05, "never nothing"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("field", ["cx", "cy", "size"])
def test_numbers_that_are_not_numbers_are_refused(bad: float, field: str) -> None:
    values = {"cx": 0.5, "cy": 0.5, "size": 0.5} | {field: bad}
    with pytest.raises(InvalidPortraitError, match="portrait"):
        fit_circle(Circle(**values), 4000, 3000)


@given(cx=anything_finite, cy=anything_finite, size=anything_finite, photo=photos())
def test_whatever_a_client_sends_becomes_a_square_inside_the_photo(
    cx: float, cy: float, size: float, photo: tuple[int, int]
) -> None:
    fitted = fit_circle(Circle(cx, cy, size), *photo)
    assert 0 < fitted.size <= 1
    assert_a_square_inside(circle_box(fitted, *photo), *photo)
    again = fit_circle(fitted, *photo)
    assert (again.cx, again.cy, again.size) == pytest.approx((fitted.cx, fitted.cy, fitted.size))


# --- the photo's size, and a face found again -------------------------------------------------


def test_the_photo_size_falls_back_to_the_thumbnail_then_to_a_square() -> None:
    assert photo_size(4000, 3000, (640, 480)) == (4000, 3000)
    assert photo_size(None, 3000, (640, 480)) == (640, 480), "same shape, which is what counts"
    assert photo_size(0, 0, None) == (1, 1)
    assert photo_size(None, None, None) == (1, 1)


def test_overlap_is_the_shared_part_of_two_boxes() -> None:
    box = BoundingBox(0.2, 0.2, 0.2, 0.2)
    assert overlap(box, box) == pytest.approx(1)
    assert overlap(box, BoundingBox(0.6, 0.6, 0.2, 0.2)) == 0
    assert overlap(box, BoundingBox(0.3, 0.2, 0.2, 0.2)) == pytest.approx(1 / 3)
    assert overlap(BoundingBox(0, 0, 0, 0), BoundingBox(0, 0, 0, 0)) == 0, "nothing to share"
