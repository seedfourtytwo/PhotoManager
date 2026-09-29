"""Integration tests against the real ExifTool and libvips."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.exiftool_reader import ExifToolReader, to_metadata
from photo_assistant.adapters.vips_renderer import VipsRenderer

pytestmark = pytest.mark.integration

needs_exiftool = pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool missing")


@pytest.fixture(scope="module")
def reader() -> Iterator[ExifToolReader]:
    r = ExifToolReader()
    yield r
    r.close()


@needs_exiftool
def test_reads_dates_camera_gps_and_offset(reader: ExifToolReader, source_guard: Path) -> None:
    (meta,) = reader.read_many([source_guard / "IMG_1001.JPG"])
    assert meta.error is None
    assert meta.dates.date_time_original == "2019:07:04 18:30:00"
    assert meta.dates.offset_time == "+02:00"
    assert (meta.camera_make, meta.camera_model) == ("Apple", "iPhone 8")
    assert meta.latitude == pytest.approx(48.8566)
    assert meta.longitude == pytest.approx(2.3522)
    assert (meta.width, meta.height) == (120, 90)
    assert meta.mime_type == "image/jpeg"


@needs_exiftool
def test_orientation_swaps_display_size(reader: ExifToolReader, source_guard: Path) -> None:
    (meta,) = reader.read_many([source_guard / "IMG_1002.JPG"])
    assert meta.orientation == 6
    assert meta.display_size == (120, 160)


@needs_exiftool
def test_png_size_comes_through(reader: ExifToolReader, source_guard: Path) -> None:
    (meta,) = reader.read_many([source_guard / "Screenshot from 2026-07-03 15-21-27.png"])
    assert (meta.width, meta.height) == (90, 160)


@needs_exiftool
def test_bad_files_get_an_error_not_an_exception(
    reader: ExifToolReader, source_guard: Path
) -> None:
    empty, text, emoji = reader.read_many(
        [
            source_guard / "empty.jpg",
            source_guard / "not-an-image.jpg",
            source_guard / "beach day 🌊.jpg",
        ]
    )
    assert empty.error is not None
    assert text.error is not None and "not an image" in text.error
    assert emoji.error is None, "unicode file names must work"


def test_mapping_handles_missing_and_junk_values() -> None:
    meta = to_metadata({"File:MIMEType": "image/jpeg", "EXIF:Orientation": "junk"})
    assert meta.orientation is None and meta.error is None
    sized = to_metadata({"File:MIMEType": "image/png", "Composite:ImageSize": "30x20"})
    assert (sized.width, sized.height) == (30, 20)
    assert to_metadata({}).error == "not an image (unknown type)"


def test_renderer_applies_orientation_and_fits_the_box(tmp_path: Path, source_guard: Path) -> None:
    out = tmp_path / "t.webp"
    size = VipsRenderer().render(source_guard / "IMG_1002.JPG", out, max_edge=64)
    assert size == (48, 64), "stored 160x120 with orientation 6 displays as portrait"
    assert out.read_bytes()[:4] == b"RIFF"


def test_renderer_never_upscales(tmp_path: Path, source_guard: Path) -> None:
    assert VipsRenderer().render(source_guard / "grey-1x1.png", tmp_path / "g.webp", 640) == (1, 1)


def test_renderer_raises_on_undecodable_files(tmp_path: Path, source_guard: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017 - pyvips raises its own Error type
        VipsRenderer().render(source_guard / "truncated.jpg", tmp_path / "t.webp", 64)
    assert list(tmp_path.glob("*.webp")) == [], "no half-written files left behind"
