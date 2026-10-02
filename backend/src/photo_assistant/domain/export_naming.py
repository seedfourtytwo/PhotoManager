"""Downloads: options, file names and folders inside a ZIP, size estimates (FEATURES 4b)."""

import itertools
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath

from photo_assistant.domain.edit_recipe import fit_within

FORMATS = ("original", "jpeg", "png", "webp")
MAX_EDGE = 20000  # pixels; larger requests overflowed libvips (QA A6)
_EXTENSIONS = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
# Size estimates start from the photo's real bytes (QA A14: bytes-per-pixel guesses were 10-30x
# too high on the synthetic library, and wrong for any photo that compresses unusually).
# Calibration: docs/PERFORMANCE.md §Download estimates (VipsRenderer, 48 synthetic photos,
# 800-4000 px, q90; WebP and PNG factors set between those and typical camera photos).
# Bytes of a q90 JPEG with the same pixels, per byte of the source file:
_AS_JPEG = {
    "image/jpeg": 1.0,
    "image/heic": 2.0,  # HEIC/AVIF/WebP keep the same picture in about half the bytes
    "image/heif": 2.0,
    "image/avif": 2.0,
    "image/webp": 1.6,
    "image/png": 2.0,
}
_AS_JPEG_OTHER = 0.25  # RAW and TIFF hold far more bytes than any JPEG of them
# Output bytes per byte of q90 JPEG, same pixels:
_FORMAT_FACTOR = {"jpeg": 0.95, "webp": 0.4, "png": 3.7}
# Bytes shrink more slowly than pixels when a photo is made smaller (more detail per pixel):
# bytes ~ pixels ** exponent (fitted on the 200/1024/2048 px renders).
_SCALE_EXPONENT = {"jpeg": 0.55, "webp": 0.5, "png": 0.8}
# JPEG/WebP size relative to quality 90 (piecewise linear between these points):
_QUALITY_CURVE = ((1, 0.1), (50, 0.35), (75, 0.55), (90, 1.0), (95, 1.5), (100, 3.0))
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
        if self.max_edge is not None and not 1 <= self.max_edge <= MAX_EDGE:
            raise OptionsError(f"max_edge must be 1 to {MAX_EDGE} pixels")

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


def _quality_factor(quality: int) -> float:
    for (q0, f0), (q1, f1) in itertools.pairwise(_QUALITY_CURVE):
        if quality <= q1:
            return f0 + (f1 - f0) * (quality - q0) / (q1 - q0)
    return _QUALITY_CURVE[-1][1]


def estimate_bytes(
    byte_size: int,
    mime_type: str | None,
    source_size: tuple[int, int] | None,
    shown_size: tuple[int, int] | None,
    output_format: str,
    options: ExportOptions,
) -> int:
    """Expected size of one download. ``source_size``: the file's pixels; ``shown_size``: after
    the edit recipe; ``output_format``: jpeg | png | webp, or original (sent untouched)."""
    if output_format == "original" or source_size is None or shown_size is None:
        return byte_size
    w, h = fit_within(*shown_size, options.max_edge)
    pixels = max(1, source_size[0] * source_size[1])
    as_jpeg = byte_size * _AS_JPEG.get(mime_type or "", _AS_JPEG_OTHER)
    quality = 1.0 if output_format == "png" else _quality_factor(options.quality)
    scale: float = math.pow(min(1.0, (w * h) / pixels), _SCALE_EXPONENT[output_format])
    return max(1, round(as_jpeg * _FORMAT_FACTOR[output_format] * quality * scale))


def skipped_manifest(failed: list[tuple[str, str]]) -> str:
    """``manifest.txt`` for a ZIP that had to leave photos out: (name, reason) each."""
    n = len(failed)
    lines = [f"{n} photo{'s' if n != 1 else ''} could not be included:", ""]
    lines += [f"- {name}: {reason}" for name, reason in failed]
    return "\n".join(lines) + "\n"
