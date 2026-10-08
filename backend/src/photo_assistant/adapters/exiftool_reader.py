"""MetadataReader backed by one long-running ExifTool process (-stay_open)."""

import re
import subprocess
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


_UNSAFE_NAME = re.compile(r"[\x00-\x1f\x7f]")
UNSAFE_NAME_REASON = (
    "unsupported file name: contains a line break or other control character; rename it"
)


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
        """Read metadata; paths that could be misread as ExifTool options are refused.

        ExifTool's -stay_open protocol takes one argument per line and cannot escape a
        newline, so a file name containing one would inject options (QA M1: it rewrote other
        photos). Control characters are refused outright; paths must be absolute so no
        argument can start with "-".
        """
        for path in paths:
            if not path.is_absolute():
                raise ValueError(f"exiftool paths must be absolute: {path!s}")
        safe = [p for p in paths if not _UNSAFE_NAME.search(str(p))]
        records = self._read_safe(safe) if safe else []
        by_path = {Path(str(r.get("SourceFile", ""))).resolve(): r for r in records}
        results = []
        for path in paths:
            if _UNSAFE_NAME.search(str(path)):
                results.append(PhotoMetadata(error=UNSAFE_NAME_REASON))
                continue
            record = by_path.get(path.resolve())
            results.append(
                to_metadata(record) if record else PhotoMetadata(error="unreadable by exiftool")
            )
        return results

    def _read_safe(self, paths: list[Path]) -> list[dict[str, Any]]:
        with self._lock:
            if not self._helper.running:
                self._helper.run()
            records: list[dict[str, Any]] = self._helper.get_tags(
                [str(p) for p in paths], tags=_TAGS
            )
        return records

    def close(self) -> None:
        with self._lock:
            if self._helper.running:
                self._helper.terminate()


# Location tags in EXIF, XMP and IPTC. Wildcards are ExifTool's own.
_LOCATION_TAGS = [
    "-gps:all=",
    "-xmp-exif:gps*=",
    "-xmp-iptcExt:Location*=",
    "-xmp-photoshop:City=",
    "-xmp-photoshop:State=",
    "-xmp-photoshop:Country=",
    "-iptc:City=",
    "-iptc:Province-State=",
    "-iptc:Country-PrimaryLocationName=",
    "-iptc:Sub-location=",
]
# Everything, but keep what changes how the photo looks (colour profile, orientation).
_ALL_TAGS = ["-all=", "-tagsfromfile", "@", "-icc_profile", "-orientation"]


class ExifToolStripper:
    """MetadataStripper: rewrites a *temporary copy* in place (never a library original)."""

    def __init__(self, executable: str = "exiftool", timeout_seconds: float = 120.0) -> None:
        self._executable = executable
        self._timeout = timeout_seconds

    def strip(self, path: Path, *, location_only: bool) -> None:
        if not path.is_absolute() or _UNSAFE_NAME.search(str(path)):
            raise ValueError(f"refusing to run exiftool on {path!r}")
        tags = _LOCATION_TAGS if location_only else _ALL_TAGS
        try:
            result = subprocess.run(  # an argument list, never a shell
                [self._executable, "-q", "-q", "-overwrite_original", *tags, str(path)],
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("exiftool took too long to strip metadata") from exc
        if result.returncode != 0:
            raise RuntimeError(f"exiftool could not strip metadata: {result.stderr.strip()}")
