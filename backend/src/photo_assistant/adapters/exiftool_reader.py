"""MetadataReader backed by one long-running ExifTool process (-stay_open)."""

import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import exiftool  # type: ignore[import-untyped]

from photo_assistant.domain.capture_time import MetadataDates
from photo_assistant.domain.model import PhotoMetadata

_TAGS = [
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "EXIF:OffsetTimeOriginal",
    "XMP:DateCreated",
    "QuickTime:CreateDate",
    "Composite:ImageSize",
    "File:ImageWidth",
    "File:ImageHeight",
    "EXIF:ExifImageWidth",
    "EXIF:ExifImageHeight",
    "EXIF:Orientation",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "EXIF:Make",
    "EXIF:Model",
    "File:MIMEType",
    "MakerNotes:ContentIdentifier",
    "QuickTime:ContentIdentifier",
]


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str | None:
    return None if value is None else str(value).strip() or None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _size(record: dict[str, Any]) -> tuple[int | None, int | None]:
    width = _int(_first(record, "File:ImageWidth", "EXIF:ExifImageWidth"))
    height = _int(_first(record, "File:ImageHeight", "EXIF:ExifImageHeight"))
    if (width is None or height is None) and isinstance(record.get("Composite:ImageSize"), str):
        parts = str(record["Composite:ImageSize"]).replace("x", " ").split()
        if len(parts) == 2:
            width, height = _int(parts[0]), _int(parts[1])
    return width, height


def to_metadata(record: dict[str, Any]) -> PhotoMetadata:
    """Map one ExifTool JSON record (``-G -n``) to our domain type."""
    mime = _text(record.get("File:MIMEType"))
    error = _text(record.get("ExifTool:Error"))
    if error is None and (mime is None or not mime.startswith("image/")):
        error = f"not an image ({mime or 'unknown type'})"
    width, height = _size(record)
    return PhotoMetadata(
        dates=MetadataDates(
            date_time_original=_text(record.get("EXIF:DateTimeOriginal")),
            create_date=_text(_first(record, "EXIF:CreateDate", "QuickTime:CreateDate")),
            offset_time=_text(record.get("EXIF:OffsetTimeOriginal")),
            xmp_date_created=_text(record.get("XMP:DateCreated")),
        ),
        width=width,
        height=height,
        orientation=_int(record.get("EXIF:Orientation")),
        latitude=_float(record.get("Composite:GPSLatitude")),
        longitude=_float(record.get("Composite:GPSLongitude")),
        camera_make=_text(record.get("EXIF:Make")),
        camera_model=_text(record.get("EXIF:Model")),
        mime_type=mime,
        live_photo_id=_text(
            _first(record, "MakerNotes:ContentIdentifier", "QuickTime:ContentIdentifier")
        ),
        error=error,
    )


class ExifToolReader:
    """Keeps one ExifTool process alive; safe to share between threads."""

    def __init__(self, executable: str = "exiftool") -> None:
        self._helper = exiftool.ExifToolHelper(
            executable=executable, common_args=["-G", "-n"], check_execute=False
        )
        self._lock = threading.Lock()

    def read_many(self, paths: Sequence[Path]) -> list[PhotoMetadata]:
        if not paths:
            return []
        with self._lock:
            if not self._helper.running:
                self._helper.run()
            records = self._helper.get_tags([str(p) for p in paths], tags=_TAGS)
        by_path = {Path(r.get("SourceFile", "")).resolve(): r for r in records}
        results = []
        for path in paths:
            record = by_path.get(path.resolve())
            if record is None:
                results.append(PhotoMetadata(error="unreadable by exiftool"))
            else:
                results.append(to_metadata(record))
        return results

    def close(self) -> None:
        with self._lock:
            if self._helper.running:
                self._helper.terminate()
