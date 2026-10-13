"""How a photo was exposed: aperture, shutter time, ISO and focal length.

Cameras and tools write these as numbers, as fractions ("28/10", "1/250"), as text with a
unit ("f/2.8", "35.0 mm") and sometimes as several values or as nonsense (0, a placeholder,
a number no camera has). Each rule here answers a clean value or None, never an error: a
photo without readable settings is still a photo.
"""

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

# Beyond these no camera or lens exists, so the value is a placeholder or a broken tag.
MAX_F_NUMBER = 512.0  # pinhole cameras sit around f/256
MAX_EXPOSURE_SECONDS = 86_400.0  # a whole day
MAX_ISO = 10_000_000  # the most sensitive cameras made stop near 4 million
MAX_FOCAL_LENGTH_MM = 10_000.0  # the longest telephoto lenses are a few metres

# A number, or a fraction of two: "2.8", "1/250", "1.5e-05". Whatever stands around it
# ("f/", "ISO", "mm", "s") is not part of it.
_NUMBER = r"-?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?"
_VALUE = re.compile(rf"({_NUMBER})(?:\s*/\s*({_NUMBER}))?")


def _from_text(text: str) -> Iterator[float]:
    for top, bottom in _VALUE.findall(text):
        try:
            yield float(top) / float(bottom) if bottom else float(top)
        except (ZeroDivisionError, OverflowError):
            continue  # "28/0": the tag is there, its value is not


def _numbers(raw: object) -> Iterator[float]:
    """Every number ``raw`` holds, in the order written."""
    if isinstance(raw, bool):
        return
    if isinstance(raw, int | float):
        try:
            yield float(raw)
        except OverflowError:
            return
    elif isinstance(raw, str):
        yield from _from_text(raw)
    elif isinstance(raw, list | tuple):
        for item in raw:
            yield from _numbers(item)


def _first_sensible(raw: object, limit: float, places: int | None) -> float | None:
    """The first number above zero and within ``limit``, rounded to ``places`` decimals."""
    for number in _numbers(raw):
        if not math.isfinite(number):
            continue
        value = number if places is None else round(number, places)
        if 0 < value <= limit:
            return value
    return None


def parse_f_number(raw: object) -> float | None:
    """The aperture as its f-number: 2.8 for f/2.8."""
    return _first_sensible(raw, MAX_F_NUMBER, 2)


def parse_exposure_time(raw: object) -> float | None:
    """The shutter time in seconds, kept exactly: 0.004 for 1/250."""
    return _first_sensible(raw, MAX_EXPOSURE_SECONDS, None)


def parse_iso(raw: object) -> int | None:
    """The sensitivity as a whole number; of several values, the first sensible one."""
    value = _first_sensible(raw, MAX_ISO, 0)
    return None if value is None else int(value)


def parse_focal_length(raw: object) -> float | None:
    """The lens's own focal length in millimetres (not the 35 mm equivalent)."""
    return _first_sensible(raw, MAX_FOCAL_LENGTH_MM, 2)


@dataclass(frozen=True, slots=True)
class Exposure:
    """Each value on its own: a scan has none, an old camera may have left one out."""

    f_number: float | None = None
    exposure_time: float | None = None  # seconds
    iso: int | None = None
    focal_length: float | None = None  # millimetres

    @classmethod
    def from_raw(
        cls, *, f_number: object, exposure_time: object, iso: object, focal_length: object
    ) -> "Exposure":
        return cls(
            parse_f_number(f_number),
            parse_exposure_time(exposure_time),
            parse_iso(iso),
            parse_focal_length(focal_length),
        )

    @property
    def is_empty(self) -> bool:
        return self == Exposure()
