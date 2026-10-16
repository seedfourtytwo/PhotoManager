"""VipsRenderer.colour_sample: the pixels a dominant colour is read from, from a thumbnail."""

from pathlib import Path

import pytest
from PIL import Image

from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.domain.colour import dominant_colour

pytestmark = pytest.mark.integration


def _two_tone(path: Path, mode: str, top: object, bottom: object) -> Path:
    """Three quarters ``top``, one quarter ``bottom``."""
    image = Image.new(mode, (64, 48), top)  # type: ignore[arg-type]
    image.paste(bottom, (0, 36, 64, 48))  # type: ignore[arg-type]
    image.save(path)
    return path


def test_a_thumbnail_gives_a_small_sample_of_its_pixels(tmp_path: Path) -> None:
    thumb = _two_tone(tmp_path / "t.webp", "RGB", (20, 60, 200), (220, 40, 40))
    sample = VipsRenderer().colour_sample(thumb)
    assert 0 < len(sample) <= 32 * 32
    assert all(len(p) == 3 and all(0 <= c <= 255 for c in p) for p in sample)
    colour = dominant_colour(sample)
    assert colour is not None
    r, _, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    assert b > 150 and r < 80, colour


def test_grey_and_transparent_pictures_give_rgb_too(tmp_path: Path) -> None:
    grey = _two_tone(tmp_path / "g.png", "L", 90, 200)
    assert dominant_colour(VipsRenderer().colour_sample(grey)) == "#5a5a5a"
    see_through = _two_tone(tmp_path / "a.png", "RGBA", (0, 128, 0, 255), (0, 0, 0, 0))
    assert dominant_colour(VipsRenderer().colour_sample(see_through)) == "#008000"
