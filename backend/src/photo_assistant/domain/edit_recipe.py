"""Non-destructive edits (FEATURES 4c): a small, validated recipe per photo.

Order of operations (the browser preview and the libvips renderer both follow it):
1. rotate by a quarter turn (clockwise), 2. flip, 3. straighten by a small angle (clockwise)
and cut away the empty corners keeping the aspect ratio, 4. crop, given as fractions of the
image after steps 1 to 3.
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass

MAX_STRAIGHTEN = 15.0
QUARTER_TURNS = (0, 90, 180, 270)
_EPSILON = 1e-9


class InvalidRecipeError(ValueError):
    """The recipe can't be applied; the message says which part is wrong."""


def _fraction(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise InvalidRecipeError(f"crop.{key} must be a number from 0 to 1")
    return float(value)


@dataclass(frozen=True, slots=True)
class Crop:
    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if min(self.x, self.y) < 0 or self.w <= 0 or self.h <= 0:
            raise InvalidRecipeError("crop needs x, y ≥ 0 and a width and height above 0")
        if self.x + self.w > 1 + _EPSILON or self.y + self.h > 1 + _EPSILON:
            raise InvalidRecipeError("crop must stay inside the photo (x + w ≤ 1, y + h ≤ 1)")

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Crop":
        return cls(*(_fraction(data, k) for k in ("x", "y", "w", "h")))


@dataclass(frozen=True, slots=True)
class Recipe:
    rotate: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    crop: Crop | None = None
    straighten: float = 0.0

    def __post_init__(self) -> None:
        if self.rotate not in QUARTER_TURNS:
            raise InvalidRecipeError("rotate must be 0, 90, 180 or 270")
        if not all(isinstance(f, bool) for f in (self.flip_horizontal, self.flip_vertical)):
            raise InvalidRecipeError("flips must be true or false")
        straight = self.straighten
        if not math.isfinite(straight) or abs(straight) > MAX_STRAIGHTEN:
            raise InvalidRecipeError("straighten must be between -15 and 15 degrees")

    @property
    def is_identity(self) -> bool:
        return self == Recipe()

    @property
    def key(self) -> str:
        """Short, stable fingerprint: names cached renders of this exact recipe."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, object]:
        crop = self.crop
        return {
            "rotate": self.rotate,
            "flip_horizontal": self.flip_horizontal,
            "flip_vertical": self.flip_vertical,
            "crop": None if crop is None else {"x": crop.x, "y": crop.y, "w": crop.w, "h": crop.h},
            "straighten": self.straighten,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Recipe":
        crop = data.get("crop")
        if crop is not None and not isinstance(crop, Mapping):
            raise InvalidRecipeError("crop must be {x, y, w, h} or null")
        straighten = data.get("straighten", 0.0)
        rotate = data.get("rotate", 0)
        if not isinstance(straighten, int | float) or not isinstance(rotate, int):
            raise InvalidRecipeError("rotate and straighten must be numbers")
        return cls(
            rotate=rotate,
            flip_horizontal=data.get("flip_horizontal", False),  # type: ignore[arg-type]
            flip_vertical=data.get("flip_vertical", False),  # type: ignore[arg-type]
            crop=Crop.from_dict(crop) if crop is not None else None,
            straighten=float(straighten),
        )


def rotated_size(width: int, height: int, rotate: int) -> tuple[int, int]:
    return (height, width) if rotate in (90, 270) else (width, height)


def straighten_scale(width: int, height: int, degrees: float) -> float:
    """How much a width x height image shrinks so that, turned by ``degrees``, its same-aspect
    centre rectangle has no empty corners."""
    theta = math.radians(abs(degrees))
    cos, sin = math.cos(theta), math.sin(theta)
    return min(width / (width * cos + height * sin), height / (width * sin + height * cos))


def edited_size(width: int, height: int, recipe: Recipe) -> tuple[int, int]:
    """Displayed size of a width x height (orientation-corrected) photo after the recipe."""
    w, h = rotated_size(width, height, recipe.rotate)
    scale = straighten_scale(w, h, recipe.straighten)
    fw, fh = w * scale, h * scale
    if recipe.crop is not None:
        fw, fh = fw * recipe.crop.w, fh * recipe.crop.h
    return max(1, round(fw)), max(1, round(fh))


def fit_within(width: int, height: int, max_edge: int | None) -> tuple[int, int]:
    """Fit the longer edge into ``max_edge``; never upscale."""
    longest = max(width, height)
    if max_edge is None or longest <= max_edge:
        return width, height
    scale = max_edge / longest
    return max(1, round(width * scale)), max(1, round(height * scale))
