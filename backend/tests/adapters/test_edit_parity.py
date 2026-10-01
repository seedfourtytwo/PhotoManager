"""The server renders an edit exactly as the web editor previews it.

The web editor (``web/src/lib/crop.ts::previewTransform``) shows a recipe with CSS on an image
centred in a frame shaped like the turned photo:
``rotate(straighten) scale(coverScale) scale(flipX, flipY) rotate(quarter turn)``, applied right
to left, then crops by fractions of that frame. ``web_source_point`` is that pipeline inverted:
for a point of the edited picture it says which pixel of the original the browser shows there.

The photo is a gradient (red = x, green = y), so the colour libvips renders at a point *is* the
original position it took the pixel from; both must agree everywhere inside the picture.
"""

import math
from pathlib import Path

import pytest
from PIL import Image

from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.domain.edit_recipe import Crop, Recipe
from photo_assistant.ports import RenderSpec

pytestmark = pytest.mark.integration

W, H = 600, 400
TOLERANCE = 6  # of 255: resampling, never a different place


def gradient(path: Path) -> Path:
    image = Image.new("RGB", (W, H))
    image.putdata([(round(255 * x / (W - 1)), round(255 * y / (H - 1)), 0)
                   for y in range(H) for x in range(W)])  # fmt: skip
    image.save(path)
    return path


def _turn(x: float, y: float, degrees: float) -> tuple[float, float]:
    """CSS rotate(): clockwise on screen (y grows downwards)."""
    t = math.radians(degrees)
    return x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)


def cover_scale(aspect: float, degrees: float) -> float:
    """``coverScale`` in web/src/lib/crop.ts."""
    t = math.radians(abs(degrees))
    return max(math.cos(t) + math.sin(t) / aspect, math.cos(t) + math.sin(t) * aspect)


def web_source_point(recipe: Recipe, u: float, v: float) -> tuple[float, float]:
    """Where in the original (pixels) the browser preview takes the point (u, v) of the result."""
    fw, fh = (H, W) if recipe.rotate in (90, 270) else (W, H)  # the frame: the turned photo
    crop = recipe.crop or Crop(0, 0, 1, 1)
    x = (crop.x + u * crop.w) * fw - fw / 2
    y = (crop.y + v * crop.h) * fh - fh / 2
    x, y = _turn(x, y, -recipe.straighten)
    zoom = cover_scale(fw / fh, recipe.straighten)
    x, y = x / zoom, y / zoom
    x, y = x * (-1 if recipe.flip_horizontal else 1), y * (-1 if recipe.flip_vertical else 1)
    x, y = _turn(x, y, -recipe.rotate)
    return x + W / 2, y + H / 2


RECIPES = {
    "quarter turn": Recipe(rotate=90),
    "turn and flip": Recipe(rotate=270, flip_horizontal=True),
    "turn, flip, crop": Recipe(rotate=90, flip_vertical=True, crop=Crop(0.1, 0.2, 0.6, 0.5)),
    "straighten and crop": Recipe(straighten=7.0, crop=Crop(0.25, 0.1, 0.5, 0.7)),
    "everything": Recipe(
        rotate=180, flip_horizontal=True, straighten=-10.0, crop=Crop(0.05, 0.3, 0.8, 0.6)
    ),
}


@pytest.mark.parametrize("name", list(RECIPES))
def test_server_render_matches_the_browser_preview(name: str, tmp_path: Path) -> None:
    recipe = RECIPES[name]
    out = tmp_path / "out.png"
    VipsRenderer().render_variant(
        gradient(tmp_path / "g.png"), out, RenderSpec(recipe=recipe, format="png")
    )
    with Image.open(out) as image:
        rendered = image.convert("RGB")
        for u in (0.15, 0.5, 0.85):
            for v in (0.15, 0.5, 0.85):
                sx, sy = web_source_point(recipe, u, v)
                px = rendered.getpixel(
                    (round(u * (rendered.width - 1)), round(v * (rendered.height - 1)))
                )
                assert isinstance(px, tuple)
                expected = (255 * sx / (W - 1), 255 * sy / (H - 1))
                assert abs(px[0] - expected[0]) <= TOLERANCE, (name, u, v, px, expected)
                assert abs(px[1] - expected[1]) <= TOLERANCE, (name, u, v, px, expected)


def test_the_result_has_the_shape_the_browser_shows(tmp_path: Path) -> None:
    recipe = RECIPES["everything"]
    out = tmp_path / "out.png"
    w, h = VipsRenderer().render_variant(
        gradient(tmp_path / "g.png"), out, RenderSpec(recipe=recipe, format="png")
    )
    assert recipe.crop is not None
    browser_aspect = (recipe.crop.w * W) / (recipe.crop.h * H)  # outputAspect() in crop.ts
    assert w / h == pytest.approx(browser_aspect, rel=0.01)
