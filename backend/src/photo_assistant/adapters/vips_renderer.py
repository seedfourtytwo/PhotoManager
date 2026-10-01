"""ImageRenderer with libvips: fast, low memory, applies EXIF orientation and edit recipes."""

import math
import os
import uuid
from collections.abc import Callable
from pathlib import Path

import pyvips  # type: ignore[import-untyped]

from photo_assistant.domain.edit_recipe import Recipe, straighten_scale
from photo_assistant.ports import RenderSpec

_ROTATIONS = {90: "d90", 180: "d180", 270: "d270"}


def _save_webp(image: pyvips.Image, path: str, spec: RenderSpec) -> None:
    image.webpsave(path, Q=spec.quality, strip=not spec.keep_metadata)


def _save_jpeg(image: pyvips.Image, path: str, spec: RenderSpec) -> None:
    if image.hasalpha():
        image = image.flatten(background=[255, 255, 255])
    image.jpegsave(path, Q=spec.quality, strip=not spec.keep_metadata, optimize_coding=True)


def _save_png(image: pyvips.Image, path: str, spec: RenderSpec) -> None:
    image.pngsave(path, strip=not spec.keep_metadata)


_SAVERS: dict[str, Callable[[pyvips.Image, str, RenderSpec], None]] = {
    "webp": _save_webp,
    "jpeg": _save_jpeg,
    "png": _save_png,
}


def _straighten(image: pyvips.Image, degrees: float) -> pyvips.Image:
    """Turn clockwise by ``degrees`` and keep the centred same-aspect rectangle."""
    width, height = image.width, image.height
    turned = image.similarity(angle=degrees)  # clockwise, canvas grows to fit
    scale = straighten_scale(width, height, degrees)
    w, h = max(1, math.floor(width * scale)), max(1, math.floor(height * scale))
    return turned.crop((turned.width - w) // 2, (turned.height - h) // 2, w, h)


def apply_recipe(image: pyvips.Image, recipe: Recipe) -> pyvips.Image:
    if recipe.rotate:
        image = image.rot(_ROTATIONS[recipe.rotate])
    if recipe.flip_horizontal:
        image = image.fliphor()
    if recipe.flip_vertical:
        image = image.flipver()
    if recipe.straighten:
        image = _straighten(image, recipe.straighten)
    if recipe.crop is not None:
        c = recipe.crop
        left, top = round(c.x * image.width), round(c.y * image.height)
        w = max(1, min(round(c.w * image.width), image.width - left))
        h = max(1, min(round(c.h * image.height), image.height - top))
        image = image.crop(left, top, w, h)
    return image


def _load_edge(spec: RenderSpec) -> int | None:
    """Decode no larger than needed: enough pixels that the final image still fills
    ``max_edge`` after the crop and straightening remove some."""
    if spec.max_edge is None:
        return None
    recipe = spec.recipe or Recipe()
    keep = 1.0
    if recipe.crop is not None:
        keep *= min(recipe.crop.w, recipe.crop.h)
    if recipe.straighten:
        keep *= math.cos(math.radians(abs(recipe.straighten))) / 2
    return math.ceil(spec.max_edge / keep)


class VipsRenderer:
    def __init__(self, quality: int = 80, concurrency: int | None = None) -> None:
        self._quality = quality
        if concurrency:
            os.environ.setdefault("VIPS_CONCURRENCY", str(concurrency))

    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        return self.render_variant(
            source, destination, RenderSpec(max_edge=max_edge, quality=self._quality)
        )

    def render_variant(self, source: Path, destination: Path, spec: RenderSpec) -> tuple[int, int]:
        saver = _SAVERS.get(spec.format)
        if saver is None:
            raise ValueError(f"unsupported output format: {spec.format!r}")
        image = self._load(source, spec)
        if spec.recipe is not None:
            if spec.max_edge is not None:
                # thumbnail() decodes top to bottom; turns and flips read rows out of order,
                # so hold the (already reduced) image in memory first.
                image = image.copy_memory()
            image = apply_recipe(image, spec.recipe)
        if spec.max_edge is not None and max(image.width, image.height) > spec.max_edge:
            image = image.resize(spec.max_edge / max(image.width, image.height))
        if image.interpretation not in ("srgb", "b-w"):
            image = image.colourspace("srgb")
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{uuid.uuid4().hex}.partial{destination.suffix}")
        try:
            saver(image, str(partial), spec)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        return int(image.width), int(image.height)

    @staticmethod
    def _load(source: Path, spec: RenderSpec) -> pyvips.Image:
        edge = _load_edge(spec)
        if edge is None:
            return pyvips.Image.new_from_file(str(source)).autorot()
        # thumbnail() decodes at a reduced size where the format allows (fast for JPEG/HEIC)
        return pyvips.Image.thumbnail(str(source), edge, height=edge, size="down")
