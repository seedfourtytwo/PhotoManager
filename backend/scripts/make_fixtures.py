"""Generate the synthetic fixture set. Every image is drawn here: no third-party content.

Run: ``uv run python scripts/make_fixtures.py`` (needs libvips and exiftool). Output is
committed so tests don't depend on the generator; rerun only when adding cases, and update
``EXPECTED`` in tests/fixtures/expected.py together with it.
"""

import shutil
import subprocess
from pathlib import Path

import pyvips  # type: ignore[import-untyped]

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "photos"


def canvas(width: int, height: int, colour: tuple[int, int, int]) -> pyvips.Image:
    """A solid image with a white bar at the top, so orientation is visible in renders."""
    image = pyvips.Image.black(width, height, bands=3) + list(colour)
    image = image.draw_rect([255, 255, 255], 0, 0, width, max(2, height // 8), fill=True)
    return image.cast("uchar").copy(interpretation="srgb")


def exif(path: Path, *args: str) -> None:
    subprocess.run(
        ["exiftool", "-q", "-overwrite_original", *args, str(path)],
        check=True,
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "nested" / "deeper").mkdir(parents=True)

    # 1. Plain camera JPEG with full EXIF date, camera and GPS.
    p = OUT / "IMG_1001.JPG"
    canvas(120, 90, (40, 90, 160)).jpegsave(str(p), Q=85)
    exif(
        p,
        "-DateTimeOriginal=2019:07:04 18:30:00",
        "-OffsetTimeOriginal=+02:00",
        "-Make=Apple",
        "-Model=iPhone 8",
        "-GPSLatitude=48.8566",
        "-GPSLatitudeRef=N",
        "-GPSLongitude=2.3522",
        "-GPSLongitudeRef=E",
    )

    # 2. Rotated: stored landscape, displayed portrait (Orientation 6 = rotate 90 CW).
    p = OUT / "IMG_1002.JPG"
    canvas(160, 120, (160, 60, 40)).jpegsave(str(p), Q=85)
    exif(p, "-DateTimeOriginal=2020:12:24 20:15:00", "-Orientation#=6")

    # 3. No EXIF at all, no date in the name -> falls back to file mtime.
    p = OUT / "nested" / "no-exif.jpg"
    canvas(100, 100, (60, 140, 60)).jpegsave(str(p), Q=85, strip=True)

    # 4. Date only in the file name (screenshot style), PNG.
    canvas(90, 160, (200, 200, 200)).pngsave(str(OUT / "Screenshot from 2026-07-03 15-21-27.png"))

    # 5. Exact duplicate under a different name and folder.
    shutil.copy2(OUT / "IMG_1001.JPG", OUT / "nested" / "deeper" / "IMG_1001 (Copy).JPG")

    # 6. Placeholder EXIF date (0000:00:00) but a date in the name.
    p = OUT / "IMG_20180312_091500.jpg"
    canvas(80, 60, (120, 120, 40)).jpegsave(str(p), Q=85)
    exif(p, "-DateTimeOriginal#=0000:00:00 00:00:00")  # "#" skips validation

    # 7. iPhone edited copy next to its original.
    p = OUT / "IMG_E1001.JPG"
    canvas(120, 90, (30, 70, 140)).jpegsave(str(p), Q=85)
    exif(p, "-DateTimeOriginal=2019:07:04 18:30:00")

    # 8. Emoji and spaces in the name.
    canvas(64, 64, (220, 120, 180)).jpegsave(str(OUT / "beach day 🌊.jpg"), Q=85)

    # 9. Things that must not become photos.
    (OUT / "empty.jpg").write_bytes(b"")
    (OUT / "not-an-image.jpg").write_bytes(b"this is text pretending to be a jpeg\n")
    (OUT / "truncated.jpg").write_bytes((OUT / "IMG_1002.JPG").read_bytes()[:200])
    (OUT / "Trip.pdf").write_bytes(b"%PDF-1.4\n% synthetic\n")
    (OUT / "IMG_1003.MOV").write_bytes(b"\x00\x00\x00\x14ftypqt  synthetic video")
    (OUT / "IMG_1001.AAE").write_text("<plist/>")
    (OUT / ".DS_Store").write_bytes(b"\x00")

    # 10. iPhone HEIC with EXIF date, plus its Live Photo video half (needs an HEVC encoder:
    #     apt install libheif-plugin-x265 — only for regenerating fixtures).
    p = OUT / "IMG_1004.HEIC"
    canvas(96, 64, (30, 120, 200)).heifsave(str(p), compression="hevc", Q=60)
    exif(p, "-DateTimeOriginal=2021:08:15 09:05:00", "-Make=Apple", "-Model=iPhone 12")
    (OUT / "IMG_1004.MOV").write_bytes(b"\x00\x00\x00\x14ftypqt  synthetic live photo")

    # 11. Smallest possible photo: 1x1 PNG.
    canvas(1, 1, (128, 128, 128)).pngsave(str(OUT / "grey-1x1.png"))

    for leftover in OUT.rglob("*_original"):
        leftover.unlink()
    print(f"wrote {sum(1 for f in OUT.rglob('*') if f.is_file())} files to {OUT}")


if __name__ == "__main__":
    main()
