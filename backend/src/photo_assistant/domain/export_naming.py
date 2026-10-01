"""Downloads: options, file names and folders inside a ZIP, size estimates (FEATURES 4b)."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath

from photo_assistant.domain.edit_recipe import fit_within

FORMATS = ("original", "jpeg", "png", "webp")
_EXTENSIONS = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
# Rough bytes per pixel, measured on photos: good enough to warn "this is 2 GB".
_BYTES_PER_PIXEL = {"jpeg": 0.45, "webp": 0.3, "png": 2.5}
_UNSAFE = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")


class Naming(StrEnum):
    ORIGINAL = "original"
    DATE = "date"


class Folders(StrEnum):
    FLAT = "flat"
    YEAR = "year"
    MONTH = "month"


class OptionsError(ValueError):
    """Download options that can't be honoured."""


@dataclass(frozen=True, slots=True)
class ExportOptions:
    format: str = "original"
    quality: int = 90
    max_edge: int | None = None
    strip_location: bool = False
    strip_all_metadata: bool = False
    naming: Naming = Naming.ORIGINAL
    folders: Folders = Folders.FLAT

    def __post_init__(self) -> None:
        if self.format not in FORMATS:
            raise OptionsError(f"format must be one of {', '.join(FORMATS)}")
        if not 1 <= self.quality <= 100:
            raise OptionsError("quality must be 1 to 100")
        if self.max_edge is not None and self.max_edge < 1:
            raise OptionsError("max_edge must be a positive number of pixels")

    @property
    def untouched(self) -> bool:
        """The original file is sent as it is (metadata may still be stripped from a copy)."""
        return self.format == "original" and self.max_edge is None


def _safe(text: str) -> str:
    return _UNSAFE.sub("_", unicodedata.normalize("NFC", text))


def export_stem(
    original_name: str, taken_at: datetime, naming: Naming, city: str | None = None
) -> str:
    if naming is Naming.DATE:
        stem = taken_at.strftime("%Y-%m-%d_%H%M%S")
        return f"{stem}_{_safe(city).replace(' ', '-')}" if city else stem
    stem = PurePosixPath(_safe(original_name)).stem
    return stem if stem and not stem.startswith(".") else "photo"


def export_extension(fmt: str, original_name: str) -> str:
    if fmt == "original":
        return PurePosixPath(original_name).suffix
    return _EXTENSIONS[fmt]


def folder_for(taken_at: datetime, folders: Folders) -> str:
    if folders is Folders.YEAR:
        return f"{taken_at:%Y}/"
    if folders is Folders.MONTH:
        return f"{taken_at:%Y}/{taken_at:%m}/"
    return ""


def unique_names(names: list[str]) -> list[str]:
    """Same order; a name seen before (ignoring case) gets ``_2``, ``_3``… before its suffix."""
    taken: set[str] = set()
    result = []
    for name in names:
        path = PurePosixPath(name)
        candidate, n = name, 1
        while candidate.lower() in taken:
            n += 1
            candidate = str(path.with_name(f"{path.stem}_{n}{path.suffix}"))
        taken.add(candidate.lower())
        result.append(candidate)
    return result


def estimate_bytes(
    byte_size: int, width: int | None, height: int | None, options: ExportOptions
) -> int:
    if options.untouched or width is None or height is None:
        return byte_size
    fmt = options.format if options.format != "original" else "jpeg"
    w, h = fit_within(width, height, options.max_edge)
    quality = options.quality / 90 if fmt != "png" else 1.0
    return max(1, round(w * h * _BYTES_PER_PIXEL[fmt] * quality))
