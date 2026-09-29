import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.faces import BoundingBox
from photo_assistant.domain.vectors import (
    cosine_distance,
    cosine_similarity,
    dot,
    mean_direction,
    normalise,
)

finite = st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False)
vectors = st.lists(finite, min_size=2, max_size=8).filter(lambda v: sum(x * x for x in v) > 1e-3)


def test_dot_and_normalise() -> None:
    assert dot((1.0, 2.0), (3.0, 4.0)) == 11.0
    assert normalise((3.0, 4.0)) == pytest.approx((0.6, 0.8))


def test_normalise_rejects_zero_vector() -> None:
    with pytest.raises(ValueError, match="zero"):
        normalise((0.0, 0.0))


def test_dot_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="dimension"):
        dot((1.0,), (1.0, 2.0))


def test_cosine_of_orthogonal_and_opposite() -> None:
    assert cosine_distance((1.0, 0.0), (0.0, 1.0)) == pytest.approx(1.0)
    assert cosine_distance((1.0, 0.0), (-2.0, 0.0)) == pytest.approx(2.0)
    assert cosine_similarity((1.0, 1.0), (2.0, 2.0)) == pytest.approx(1.0)


@given(vectors)
def test_normalised_vectors_have_unit_length(v: list[float]) -> None:
    assert math.fsum(x * x for x in normalise(tuple(v))) == pytest.approx(1.0)


@given(vectors, vectors)
def test_cosine_distance_is_symmetric_and_bounded(a: list[float], b: list[float]) -> None:
    n = min(len(a), len(b))
    a2, b2 = tuple(a[:n]), tuple(b[:n])
    if math.fsum(x * x for x in a2) < 1e-3 or math.fsum(x * x for x in b2) < 1e-3:
        return
    d = cosine_distance(a2, b2)
    assert d == pytest.approx(cosine_distance(b2, a2))
    assert -1e-9 <= d <= 2 + 1e-9


def test_mean_direction_is_normalised_average() -> None:
    assert mean_direction([(1.0, 0.0), (0.0, 1.0)]) == pytest.approx(
        (math.sqrt(0.5), math.sqrt(0.5))
    )
    with pytest.raises(ValueError, match="empty"):
        mean_direction([])


def test_bounding_box_is_clamped_to_the_image() -> None:
    box = BoundingBox.from_pixels(-10, 20, 110, 70, width=100, height=100)
    assert (box.x, box.y, box.width, box.height) == pytest.approx((0.0, 0.2, 1.0, 0.5))


def test_bounding_box_rejects_non_positive_image_size() -> None:
    with pytest.raises(ValueError, match="image size"):
        BoundingBox.from_pixels(0, 0, 1, 1, width=0, height=10)
