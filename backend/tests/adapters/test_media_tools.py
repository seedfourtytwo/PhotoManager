"""Integration tests against the real ExifTool and libvips."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.exiftool_reader import ExifToolReader, to_metadata
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.domain.exposure import Exposure
from tests.synthetic import write_photo

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


@needs_exiftool
def test_reads_aperture_shutter_iso_and_focal_length(
    reader: ExifToolReader, tmp_path: Path
) -> None:
    shot = Exposure(f_number=2.8, exposure_time=1 / 250, iso=400, focal_length=35.0)
    slow = Exposure(f_number=11.0, exposure_time=2.5, iso=64, focal_length=4.25)
    first, second = reader.read_many(
        [
            write_photo(tmp_path / "shot.jpg", seed=1, exposure=shot),
            write_photo(tmp_path / "slow.jpg", seed=2, exposure=slow),
        ]
    )
    assert first.exposure == shot
    assert second.exposure == slow


@needs_exiftool
def test_reads_the_exposure_values_a_photo_has_and_leaves_the_others_empty(
    reader: ExifToolReader, tmp_path: Path
) -> None:
    only_iso = write_photo(tmp_path / "iso.jpg", seed=3, exposure=Exposure(iso=800))
    (meta,) = reader.read_many([only_iso])
    assert meta.exposure == Exposure(iso=800)


@needs_exiftool
def test_a_photo_without_exposure_tags_has_an_empty_exposure(
    reader: ExifToolReader, source_guard: Path
) -> None:
    camera, screenshot = reader.read_many(
        [source_guard / "IMG_1001.JPG", source_guard / "Screenshot from 2026-07-03 15-21-27.png"]
    )
    assert camera.exposure.is_empty and screenshot.exposure.is_empty


def test_mapping_reads_exposure_through_the_domain_rules() -> None:
    meta = to_metadata(
        {
            "File:MIMEType": "image/jpeg",
            "EXIF:FNumber": 0,
            "EXIF:ExposureTime": "1/250",
            "EXIF:ISO": "100 200",
            "EXIF:FocalLength": "junk",
        }
    )
    assert meta.exposure == Exposure(exposure_time=0.004, iso=100)


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


def test_reader_refuses_control_characters_without_calling_exiftool(tmp_path: Path) -> None:
    class Exploding(ExifToolReader):
        def __init__(self) -> None:  # no process at all
            pass

        def _read_safe(self, paths: list[Path]) -> list[dict[str, object]]:
            raise AssertionError("exiftool must not be called")

    (meta,) = Exploding().read_many([tmp_path / "a\nb.jpg"])
    assert meta.error is not None and "file name" in meta.error


def test_reader_requires_absolute_paths(reader: ExifToolReader) -> None:
    with pytest.raises(ValueError, match="absolute"):
        reader.read_many([Path("-all=.jpg")])
