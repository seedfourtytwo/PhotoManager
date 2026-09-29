"""Faces as the rest of the app sees them: geometry in fractions of the displayed image."""

from dataclasses import dataclass

from photo_assistant.domain.vectors import Vector


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
