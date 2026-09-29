"""ImageRenderer with libvips: fast, low memory, applies EXIF orientation."""

import os
import uuid
from pathlib import Path

import pyvips  # type: ignore[import-untyped]


class VipsRenderer:
    def __init__(self, quality: int = 80, concurrency: int | None = None) -> None:
        self._quality = quality
        if concurrency:
            os.environ.setdefault("VIPS_CONCURRENCY", str(concurrency))

    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        image = pyvips.Image.thumbnail(
            str(source), max_edge, height=max_edge, size="down", no_rotate=False
        )
        if image.interpretation not in ("srgb", "b-w"):
            image = image.colourspace("srgb")
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{uuid.uuid4().hex}.partial.webp")
        try:
            image.webpsave(str(partial), Q=self._quality, strip=True)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        return int(image.width), int(image.height)
