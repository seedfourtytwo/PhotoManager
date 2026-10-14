"""Synthetic test photos drawn on the fly (never real photos): colour, EXIF date, GPS, camera,
exposure settings."""

import random
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw
from PIL.ExifTags import GPS, IFD, Base
from PIL.TiffImagePlugin import IFDRational

from photo_assistant.domain.exposure import Exposure


def _dms(value: float) -> tuple[float, float, float]:
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60, 4)
    return (float(degrees), float(minutes), seconds)


def _rational(value: float) -> IFDRational:
    """As a camera writes it: a fraction of two whole numbers (1/250, 28/10)."""
    fraction = Fraction(value).limit_denominator(100_000)
    return IFDRational(fraction.numerator, fraction.denominator)


def _exposure_tags(exposure: Exposure) -> dict[int, object]:
    tags: dict[int, object] = {}
    if exposure.f_number is not None:
        tags[Base.FNumber] = _rational(exposure.f_number)
    if exposure.exposure_time is not None:
        tags[Base.ExposureTime] = _rational(exposure.exposure_time)
    if exposure.iso is not None:
        tags[Base.ISOSpeedRatings] = exposure.iso
    if exposure.focal_length is not None:
        tags[Base.FocalLength] = _rational(exposure.focal_length)
    return tags


def write_photo(
    path: Path,
    *,
    seed: int,
    size: tuple[int, int] = (96, 64),
    taken: datetime | None = None,
    gps: tuple[float, float] | None = None,
    camera: str | None = None,
    exposure: Exposure | None = None,
    image: Image.Image | None = None,
) -> Path:
    """A small JPEG whose pixels depend on ``seed`` (so every seed is a different photo)."""
    if image is None:
        rng = random.Random(seed)
        image = Image.new("RGB", size, tuple(rng.randrange(256) for _ in range(3)))
        draw = ImageDraw.Draw(image)
        for _ in range(6):
            x, y = rng.randrange(size[0]), rng.randrange(size[1])
            colour = tuple(rng.randrange(256) for _ in range(3))
            draw.rectangle((x, y, x + size[0] // 3, y + size[1] // 3), fill=colour)
    exif = Image.Exif()
    if taken is not None:
        stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
        exif[Base.DateTime] = stamp
        exif.get_ifd(IFD.Exif)[Base.DateTimeOriginal] = stamp
    if camera is not None:
        exif[Base.Make] = "Synthetic"
        exif[Base.Model] = camera
    if exposure is not None:
        exif.get_ifd(IFD.Exif).update(_exposure_tags(exposure))
    if gps is not None:
        lat, lon = gps
        exif.get_ifd(IFD.GPSInfo).update(
            {
                GPS.GPSLatitudeRef: "N" if lat >= 0 else "S",
                GPS.GPSLatitude: _dms(lat),
                GPS.GPSLongitudeRef: "E" if lon >= 0 else "W",
                GPS.GPSLongitude: _dms(lon),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "JPEG", quality=90, exif=exif)
    return path
