"""When was this photo taken? The fallback chain from FEATURES 2.2.

Order of trust: EXIF DateTimeOriginal → EXIF CreateDate → XMP DateCreated → a date in the file
name → the file's modification time. Every result records which source won, so the UI can show
"date guessed from file" and the user can fix it.

Times are kept as *local wall-clock* time (what the camera showed) plus an optional UTC offset,
because most cameras don't record a timezone and converting would shift photos across midnight.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import PurePath

EARLIEST_PLAUSIBLE = datetime(1826, 1, 1)  # the first surviving photograph
FUTURE_TOLERANCE = timedelta(days=1)


class DateSource(StrEnum):
    EXIF = "exif"
    EXIF_CREATE = "exif_create"
    XMP = "xmp"
    FILENAME = "filename"
    FILE_MTIME = "file_mtime"


@dataclass(frozen=True, slots=True)
class MetadataDates:
    """Raw date strings as read from the file; any of them may be missing or junk."""

    date_time_original: str | None = None
    create_date: str | None = None
    offset_time: str | None = None
    xmp_date_created: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureTime:
    value: datetime  # naive, local wall-clock time
    tz_offset_minutes: int | None
    source: DateSource


_EXIF = re.compile(
    r"^\s*(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?"
    r"(?:\.\d+)?\s*(Z|[+\-]\d{2}:?\d{2})?\s*$"
)
_OFFSET = re.compile(r"^\s*(Z|([+\-])(\d{2}):?(\d{2}))\s*$")

# Most specific first. Each captures year, month, day and optionally hour, minute, second.
_FILENAME_PATTERNS = [
    # 20251108_100559 · IMG_20190704_183000 · PXL_20230101_120000123 · Screenshot_20200101-123456
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})[_\-](\d{2})(\d{2})(\d{2})(?!\d{0,2}\d{4})"),
    # 2015-02-02 15.53.11 · Screenshot from 2026-07-03 15-21-27
    # WhatsApp Image 2020-10-26 at 12.34.56
    re.compile(
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:[ _T]|\sat\s)(\d{2})[.\-:](\d{2})[.\-:](\d{2})(?!\d)"
    ),
    # VID-20200101-WA0001 (date only)
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})-WA\d+"),
]


def _build(parts: tuple[str | None, ...]) -> datetime | None:
    numbers = [int(p) for p in parts if p is not None]
    try:
        return datetime(*numbers)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_offset(raw: str | None) -> int | None:
    """``+02:00`` → 120. ``Z`` → 0. Anything else → None."""
    if not raw:
        return None
    match = _OFFSET.match(raw)
    if not match:
        return None
    if match.group(1) == "Z":
        return 0
    sign = -1 if match.group(2) == "-" else 1
    return sign * (int(match.group(3)) * 60 + int(match.group(4)))


def parse_exif_datetime(raw: str | None) -> tuple[datetime, int | None] | None:
    """Parse an EXIF/XMP date string; placeholder dates like ``0000:00:00`` give None."""
    if not raw:
        return None
    match = _EXIF.match(raw)
    if not match:
        return None
    value = _build(match.groups()[:6])
    if value is None:
        return None
    return value, parse_offset(match.group(7))


def date_from_filename(filename: str) -> datetime | None:
    name = PurePath(filename).stem
    for pattern in _FILENAME_PATTERNS:
        match = pattern.search(name)
        if match:
            value = _build(match.groups())
            if value is not None:
                return value
    return None


def _plausible(value: datetime, now: datetime) -> bool:
    return EARLIEST_PLAUSIBLE <= value <= now.replace(tzinfo=None) + FUTURE_TOLERANCE


def pick_capture_time(
    dates: MetadataDates, *, filename: str, file_mtime: datetime, now: datetime
) -> CaptureTime:
    """Apply the fallback chain. ``file_mtime`` and ``now`` must be timezone-aware."""
    candidates = [
        (dates.date_time_original, DateSource.EXIF),
        (dates.create_date, DateSource.EXIF_CREATE),
        (dates.xmp_date_created, DateSource.XMP),
    ]
    for raw, source in candidates:
        parsed = parse_exif_datetime(raw)
        if parsed and _plausible(parsed[0], now):
            value, inline_offset = parsed
            offset = inline_offset
            if offset is None and source is DateSource.EXIF:
                offset = parse_offset(dates.offset_time)
            return CaptureTime(value, offset, source)

    from_name = date_from_filename(filename)
    if from_name and _plausible(from_name, now):
        return CaptureTime(from_name, None, DateSource.FILENAME)

    utc = file_mtime.astimezone(UTC).replace(tzinfo=None)
    clamped = min(max(utc, EARLIEST_PLAUSIBLE), now.astimezone(UTC).replace(tzinfo=None))
    return CaptureTime(clamped, 0, DateSource.FILE_MTIME)
