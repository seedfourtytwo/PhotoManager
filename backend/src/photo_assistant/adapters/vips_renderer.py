"""ImageRenderer with libvips: fast, low memory, applies EXIF orientation and edit recipes."""

import math
import os
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pyvips  # type: ignore[import-untyped]

from photo_assistant.domain.edit_recipe import Recipe, straighten_scale
from photo_assistant.domain.export_naming import MAX_EDGE
from photo_assistant.ports import RenderSpec

_ROTATIONS = {90: "d90", 180: "d180", 270: "d270"}
# Never ask libvips to decode at more than this edge (it only shrinks, never upscales):
# a tiny crop divides the wanted edge by a tiny fraction (QA A6).
_MAX_DECODE_EDGE = 100_000


# libwebp's effort 0-6: 2 halves a 2048 px preview's encode time against the default 4
# (413 -> 225 ms per 12 MP photo on the dev machine) for a few percent more bytes (C28).
WEBP_EFFORT = 2


def _save_webp(image: pyvips.Image, path: str, spec: RenderSpec) -> None:
    image.webpsave(path, Q=spec.quality, strip=not spec.keep_metadata, effort=WEBP_EFFORT)


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
        # at least one pixel, inside the image, however small or close to the edge
        left = min(round(c.x * image.width), image.width - 1)
        top = min(round(c.y * image.height), image.height - 1)
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
    return min(math.ceil(spec.max_edge / keep), _MAX_DECODE_EDGE)


class VipsRenderer:
    def __init__(self, quality: int = 80, concurrency: int | None = None) -> None:
        self._quality = quality
        # libvips read VIPS_CONCURRENCY when it was loaded (the import above), so setting the
        # variable now would do nothing: use its setter. A variable the user set still wins.
        if concurrency and "VIPS_CONCURRENCY" not in os.environ:
            pyvips.concurrency_set(concurrency)

    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        return self.render_variant(
            source, destination, RenderSpec(max_edge=max_edge, quality=self._quality)
        )

    def render_pair(
        self,
        source: Path,
        big: Path,
        big_edge: int,
        small: Path,
        small_edge: int,
        recipe: Recipe | None = None,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """A preview and a thumbnail (WebP) from ONE decode of ``source`` (C28), with the edit
        recipe applied if any: the small one is shrunk from the big one. Returns both sizes."""
        image = self._load(source, RenderSpec(recipe=recipe, max_edge=big_edge)).copy_memory()
        if recipe is not None:
            image = apply_recipe(image, recipe)
        if max(image.width, image.height) > big_edge:
            image = image.resize(big_edge / max(image.width, image.height))
        if image.interpretation not in ("srgb", "b-w"):
            image = image.colourspace("srgb")
        spec = RenderSpec(quality=self._quality)
        self._save(image, big, spec)
        scale = min(1.0, small_edge / max(image.width, image.height))
        thumb = image.resize(scale) if scale < 1 else image
        self._save(thumb, small, spec)
        return (int(image.width), int(image.height)), (int(thumb.width), int(thumb.height))

    @staticmethod
    def _save(image: pyvips.Image, destination: Path, spec: RenderSpec) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # ends in .partial (exports, backups and the start-up sweep know that name) and sits
        # beside the destination, so the rename is atomic
        partial = destination.with_name(f".{uuid.uuid4().hex}{destination.suffix}.partial")
        try:
            _SAVERS[spec.format](image, str(partial), spec)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)

    def dimensions(self, image: Path) -> tuple[int, int]:
        header = pyvips.Image.new_from_file(str(image))  # reads the header only
        return int(header.width), int(header.height)

    def render_variant(self, source: Path, destination: Path, spec: RenderSpec) -> tuple[int, int]:
        saver = _SAVERS.get(spec.format)
        if saver is None:
            raise ValueError(f"unsupported output format: {spec.format!r}")
        if spec.max_edge is not None and spec.max_edge > MAX_EDGE:
            spec = replace(spec, max_edge=MAX_EDGE)
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
        self._save(image, destination, spec)
        return int(image.width), int(image.height)

    @staticmethod
    def _load(source: Path, spec: RenderSpec) -> pyvips.Image:
        edge = _load_edge(spec)
        if edge is None:
            return pyvips.Image.new_from_file(str(source)).autorot()
        # thumbnail() decodes at a reduced size where the format allows (fast for JPEG/HEIC)
        return pyvips.Image.thumbnail(str(source), edge, height=edge, size="down")
