"""Faces as the rest of the app sees them: geometry in fractions of the displayed image."""

import math
from dataclasses import dataclass

from photo_assistant.domain.edit_recipe import MIN_CROP
from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.vectors import Vector

# The automatic portrait: a square this many times the larger side of the face box, moved up
# by this share of that side. Detectors box the face from brow to chin; the hair is above.
_PORTRAIT_FACES = 2.0
_PORTRAIT_LIFT = 0.12
MIN_PORTRAIT_SIZE = 0.02  # of the photo's shorter edge: a portrait is never a speck


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Top-left corner plus size, each a fraction (0 to 1) of the image, so any rendition works."""

    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_pixels(
        cls, x1: float, y1: float, x2: float, y2: float, *, width: int, height: int
    ) -> "BoundingBox":
        if width <= 0 or height <= 0:
            raise ValueError(f"image size must be positive, got {width}x{height}")
        left, top = _clamp(x1 / width), _clamp(y1 / height)
        right, bottom = _clamp(x2 / width), _clamp(y2 / height)
        return cls(left, top, right - left, bottom - top)


Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Face:
    """One detected face. ``landmarks``: eyes, nose, mouth corners (fractions, 5 points)."""

    box: BoundingBox
    score: float
    landmarks: tuple[Point, ...]
    embedding: Vector


def overlap(a: BoundingBox, b: BoundingBox) -> float:
    """How much two boxes are the same box: shared area over covered area, 0 to 1."""
    shared_w = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    shared_h = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if shared_w <= 0 or shared_h <= 0:
        return 0.0
    shared = shared_w * shared_h
    return shared / (a.width * a.height + b.width * b.height - shared)


class InvalidPortraitError(InvalidError):
    """The circle sent for a portrait is not made of numbers."""


@dataclass(frozen=True, slots=True)
class Circle:
    """A round portrait on a photo as displayed, without its edits: the centre as fractions
    of the width and height, and ``size``, the side of the square round it as a fraction of
    the photo's shorter edge (1 = the largest circle the photo holds)."""

    cx: float
    cy: float
    size: float


def photo_size(
    width: int | None, height: int | None, thumb_size: tuple[int, int] | None
) -> tuple[int, int]:
    """The displayed size of a photo for placing a circle on it. Only its shape counts, so
    the thumbnail's stands in for an unknown one, and a square when nothing is known."""
    if width and height:
        return width, height
    return thumb_size or (1, 1)


def fit_circle(circle: Circle, width: int, height: int) -> Circle:
    """The nearest circle that lies inside a width x height photo and is not a speck.
    Numbers out of range are brought in; ``InvalidPortraitError`` for what is not a number."""
    if not all(math.isfinite(v) for v in (circle.cx, circle.cy, circle.size)):
        raise InvalidPortraitError("a portrait needs numbers for its centre and its size")
    short, long = min(width, height), max(width, height)
    # the renderer keeps at least MIN_CROP of each side, which on a long strip is more
    smallest = min(1.0, max(MIN_PORTRAIT_SIZE, MIN_CROP * long / short))
    size = min(1.0, max(smallest, circle.size))
    half_w, half_h = size * short / width / 2, size * short / height / 2
    return Circle(
        min(1 - half_w, max(half_w, circle.cx)), min(1 - half_h, max(half_h, circle.cy)), size
    )


def automatic_circle(box: BoundingBox, width: int, height: int) -> Circle:
    """The portrait nobody chose: a square about twice the face, with more room above it
    for the hair, as large as the photo allows and inside it."""
    face = max(box.width * width, box.height * height)
    return fit_circle(
        Circle(
            box.x + box.width / 2,
            box.y + box.height / 2 - _PORTRAIT_LIFT * face / height,
            _PORTRAIT_FACES * face / min(width, height),
        ),
        width,
        height,
    )


def circle_box(circle: Circle, width: int, height: int) -> BoundingBox:
    """The square round a circle as fractions of the photo: square in pixels, so its width
    and height differ as fractions unless the photo is square. Always inside the photo."""
    fitted = fit_circle(circle, width, height)
    side = fitted.size * min(width, height)
    w, h = side / width, side / height
    return BoundingBox(max(0.0, fitted.cx - w / 2), max(0.0, fitted.cy - h / 2), w, h)
