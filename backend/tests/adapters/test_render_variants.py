"""libvips renders edits, sizes and formats; ExifTool strips metadata from temp copies."""

from pathlib import Path

import pytest
from PIL import Image

from photo_assistant.adapters.exiftool_reader import ExifToolReader, ExifToolStripper
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.domain.edit_recipe import Crop, Recipe, edited_size
from photo_assistant.ports import RenderSpec
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


def halves(path: Path, top: str, bottom: str, size: tuple[int, int] = (200, 100)) -> Path:
    """Top half one colour, bottom half another: shows where a turn or flip moved things."""
    image = Image.new("RGB", size, top)
    image.paste(Image.new("RGB", (size[0], size[1] // 2), bottom), (0, size[1] // 2))
    return write_photo(path, seed=0, image=image, camera="Test Cam", gps=(48.85, 2.35))


def pixel(path: Path, x: float, y: float) -> tuple[int, int, int]:
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        value: tuple[int, int, int] = rgb.getpixel(
            (int(x * (im.width - 1)), int(y * (im.height - 1)))
        )  # type: ignore[assignment]
        return value


def is_red(rgb: tuple[int, int, int]) -> bool:
    return rgb[0] > 180 and rgb[2] < 80


def is_blue(rgb: tuple[int, int, int]) -> bool:
    return rgb[2] > 180 and rgb[0] < 80


@pytest.fixture
def renderer() -> VipsRenderer:
    return VipsRenderer()


def test_quarter_turn_is_clockwise(renderer: VipsRenderer, tmp_path: Path) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue")
    out = tmp_path / "out.webp"
    size = renderer.render_variant(source, out, RenderSpec(recipe=Recipe(rotate=90)))
    assert size == (100, 200)
    assert is_red(pixel(out, 0.9, 0.5)) and is_blue(pixel(out, 0.1, 0.5)), "top went right"


def test_flips(renderer: VipsRenderer, tmp_path: Path) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue")
    out = tmp_path / "out.webp"
    renderer.render_variant(source, out, RenderSpec(recipe=Recipe(flip_vertical=True)))
    assert is_blue(pixel(out, 0.5, 0.1)) and is_red(pixel(out, 0.5, 0.9))
    renderer.render_variant(source, out, RenderSpec(recipe=Recipe(flip_horizontal=True)))
    assert is_red(pixel(out, 0.5, 0.1)), "left-right flip keeps top and bottom"


def test_crop_and_straighten_match_the_size_maths(renderer: VipsRenderer, tmp_path: Path) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue", (400, 300))
    out = tmp_path / "out.webp"
    crop = Recipe(crop=Crop(0, 0.5, 0.5, 0.5))
    assert renderer.render_variant(source, out, RenderSpec(recipe=crop)) == (200, 150)
    assert is_blue(pixel(out, 0.5, 0.5)), "the bottom-left quarter"
    tilted = Recipe(straighten=10)
    w, h = renderer.render_variant(source, out, RenderSpec(recipe=tilted))
    ew, eh = edited_size(400, 300, tilted)
    assert abs(w - ew) <= 1 and abs(h - eh) <= 1
    corner = pixel(out, 0, 0)
    assert corner != (0, 0, 0), "no empty corners after straightening"


def test_resize_never_upscales(renderer: VipsRenderer, tmp_path: Path) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue", (400, 300))
    out = tmp_path / "out.webp"
    assert renderer.render_variant(source, out, RenderSpec(max_edge=100)) == (100, 75)
    assert renderer.render_variant(source, out, RenderSpec(max_edge=4000)) == (400, 300)
    recipe = Recipe(rotate=90, crop=Crop(0, 0, 1, 0.5))
    assert renderer.render_variant(source, out, RenderSpec(recipe=recipe, max_edge=100)) == (
        100,
        67,
    )


@pytest.mark.parametrize(
    ("fmt", "magic"), [("jpeg", b"\xff\xd8"), ("png", b"\x89PNG"), ("webp", b"RIFF")]
)
def test_formats(renderer: VipsRenderer, tmp_path: Path, fmt: str, magic: bytes) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue")
    out = tmp_path / f"out.{fmt}"
    renderer.render_variant(source, out, RenderSpec(format=fmt, quality=70))
    assert out.read_bytes().startswith(magic)


def test_unknown_format_is_refused(renderer: VipsRenderer, tmp_path: Path) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue")
    with pytest.raises(ValueError, match="format"):
        renderer.render_variant(source, tmp_path / "x.gif", RenderSpec(format="gif"))


def test_metadata_kept_or_stripped(renderer: VipsRenderer, tmp_path: Path) -> None:
    source = halves(tmp_path / "in.jpg", "red", "blue")
    kept, stripped = tmp_path / "kept.jpg", tmp_path / "stripped.jpg"
    renderer.render_variant(source, kept, RenderSpec(format="jpeg", keep_metadata=True))
    renderer.render_variant(source, stripped, RenderSpec(format="jpeg"))
    reader = ExifToolReader()
    try:
        meta_kept, meta_stripped = reader.read_many([kept, stripped])
    finally:
        reader.close()
    assert meta_kept.camera_model == "Test Cam" and meta_kept.latitude is not None
    assert meta_stripped.camera_model is None and meta_stripped.latitude is None


def test_exiftool_strips_location_or_everything_from_a_copy(tmp_path: Path) -> None:
    a = halves(tmp_path / "a.jpg", "red", "blue")
    b = halves(tmp_path / "b.jpg", "red", "blue")
    stripper = ExifToolStripper()
    stripper.strip(a, location_only=True)
    stripper.strip(b, location_only=False)
    reader = ExifToolReader()
    try:
        meta_a, meta_b = reader.read_many([a, b])
    finally:
        reader.close()
    assert meta_a.latitude is None and meta_a.camera_model == "Test Cam"
    assert meta_b.latitude is None and meta_b.camera_model is None
    assert meta_b.width == 200, "still a valid image"


def test_an_edit_of_a_photo_larger_than_the_preview_renders(
    renderer: VipsRenderer, tmp_path: Path
) -> None:
    """thumbnail() streams the file top to bottom; a quarter turn reads it out of order."""
    source = write_photo(tmp_path / "big.jpg", seed=3, size=(2400, 1600))
    out = tmp_path / "out.webp"
    for recipe in (Recipe(rotate=90), Recipe(straighten=5.0), Recipe(flip_vertical=True)):
        size = renderer.render_variant(source, out, RenderSpec(recipe=recipe, max_edge=2048))
        assert max(size) == 2048
