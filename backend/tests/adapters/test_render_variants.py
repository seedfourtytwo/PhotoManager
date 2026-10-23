"""libvips renders edits, sizes and formats; ExifTool strips metadata from temp copies."""

import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

from photo_assistant.adapters.exiftool_reader import ExifToolReader, ExifToolStripper
from photo_assistant.adapters.vips_renderer import MAX_DECODE_PIXELS, VipsRenderer
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


def test_a_tiny_crop_at_the_edge_and_a_huge_max_edge_still_render(
    renderer: VipsRenderer, tmp_path: Path
) -> None:
    """QA A6: the smallest crop in the far corner keeps one pixel; a huge max_edge is capped
    instead of overflowing libvips."""
    source = halves(tmp_path / "in.jpg", "red", "blue")
    corner = Recipe(crop=Crop(0.999, 0.999, 0.001, 0.001))
    size = renderer.render_variant(source, tmp_path / "c.png", RenderSpec(corner, format="png"))
    assert size == (1, 1)
    spec = RenderSpec(corner, max_edge=10**9, format="jpeg")
    assert renderer.render_variant(source, tmp_path / "big.jpg", spec) == (1, 1)


def test_a_pair_is_decoded_once_and_written_at_both_sizes(
    renderer: VipsRenderer, tmp_path: Path
) -> None:
    """C28: a thumbnail and a preview from one decode."""
    source = halves(tmp_path / "in.jpg", "red", "blue", size=(1200, 800))
    big, small = renderer.render_pair(source, tmp_path / "p.webp", 600, tmp_path / "t.webp", 150)
    assert (big, small) == ((600, 400), (150, 100))
    with Image.open(tmp_path / "p.webp") as p, Image.open(tmp_path / "t.webp") as t:
        assert p.size == (600, 400) and t.size == (150, 100)
    assert is_red(pixel(tmp_path / "t.webp", 0.5, 0.1)) and is_blue(
        pixel(tmp_path / "t.webp", 0.5, 0.9)
    )


def test_webp_derivatives_use_the_fast_encoder_effort(
    renderer: VipsRenderer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C28: effort 2 halves the preview encode time (413 -> 225 ms per 12 MP photo)."""
    import pyvips  # type: ignore[import-untyped]

    seen: list[dict[str, object]] = []
    real = pyvips.Image.webpsave

    def spy(self, path, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(kwargs)
        return real(self, path, **kwargs)

    monkeypatch.setattr(pyvips.Image, "webpsave", spy)
    renderer.render(halves(tmp_path / "in.jpg", "red", "blue"), tmp_path / "o.webp", 50)
    assert seen and all(k["effort"] == 2 for k in seen)


def _png_header(path: Path, width: int, height: int) -> Path:
    """A PNG that says it is width x height but holds one row: a hundred bytes that would
    take libvips minutes to decode, the shape of a decompression bomb."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data)
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit grey
    row = zlib.compress(b"\0" * (width + 1))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", row) + chunk(b"IEND", b"")
    )
    return path


def test_the_largest_camera_photos_stay_under_the_pixel_ceiling() -> None:
    assert MAX_DECODE_PIXELS > 19_008 * 12_672, "a 240 MP pixel-shift shot still imports"


def test_an_image_over_the_pixel_ceiling_is_refused_before_it_is_decoded(
    renderer: VipsRenderer, tmp_path: Path
) -> None:
    bomb = _png_header(tmp_path / "bomb.png", 40_000, 40_000)
    out = tmp_path / "out.webp"
    calls = (
        lambda: renderer.render(bomb, out, 640),
        lambda: renderer.render_variant(bomb, out, RenderSpec(max_edge=None)),
        lambda: renderer.render_pair(bomb, out, 2048, tmp_path / "t.webp", 640),
    )
    for call in calls:
        with pytest.raises(ValueError, match="megapixels"):
            call()
    assert not out.exists()
