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
    MANUAL = "manual"  # fixed by a person (FEATURES 2.12)


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
    r"^\s*(\d{4})[:\-](\d{2})[:\-](\d{2})"
    r"(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?"
    r"\s*(Z|[+\-]\d{2}:?\d{2})?\s*$"
)
_OFFSET = re.compile(r"^\s*(Z|([+\-])(\d{2}):?(\d{2}))\s*$")

# Digits in a file name are too often something else, so a date written without separators
# (20190704) is only believed inside these years. A dashed date (1975-06-01) is deliberate
# enough to be believed back to the first photograph: scanned family photos are named that
# way. The exception is a dashed date glued to a number group before it, which gets the strict
# years again: 1080-1920-01-02 is a picture size, not 2 January 1920.
FILENAME_EARLIEST = datetime(1990, 1, 1)
FILENAME_LATEST = datetime(2100, 1, 1)
_GLUED = re.compile(r"\d-$")

# Tried in order; within a pattern every match is tried until one is a plausible date.
_COMPACT_DATETIMES = [
    # 20251108_100559 · IMG_20190704_183000 · PXL_20230101_120000123 · Screenshot_20200101-123456
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})[_\-](\d{2})(\d{2})(\d{2})(?!\d{0,2}\d{4})"),
]
_DASHED_DATETIMES = [
    # 2015-02-02 15.53.11 · Screenshot from 2026-07-03 15-21-27 · signal-2021-05-01-12-34-56-789
    # WhatsApp Image 2020-10-26 at 12.34.56 · Screenshot 2024-03-10 at 9.15.22 AM (12-hour clock)
    re.compile(
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:[ _T\-]|\sat\s)(\d{1,2})[.\-:](\d{2})[.\-:](\d{2})(?!\d)"
        r"(?:\s?(?P<half>[AaPp])[Mm](?![A-Za-z]))?"
    ),
    # signal-2021-05-01-123456
    re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[ _T\-](\d{2})(\d{2})(\d{2})(?!\d)"),
]
# FB_IMG_1591234567890 · mmexport1591234567890 (milliseconds since 1970, UTC)
_FILENAME_EPOCH_MS = re.compile(r"(?:FB_IMG_|mmexport)(\d{13})(?!\d)")
_DASHED_DATES = [re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")]  # scan_2019-07-04
_COMPACT_DATES = [
    # DSC_20190704 · VID-20200101-WA0001. A following long number is ruled out, so Facebook
    # ids like 20151012_903634589713690_n are not read as dates.
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)(?![_\-]\d{6})"),
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


def _in_name(match: re.Match[str]) -> datetime | None:
    """The date a file-name pattern matched; an hour with AM/PM is read on the 12-hour clock."""
    half = match.groupdict().get("half")
    numbers = [int(part) for part in match.groups()[:6]]
    if half is not None and 1 <= numbers[3] <= 12:  # "13.15 PM" is already on the 24-hour clock
        numbers[3] = numbers[3] % 12 + (12 if half in "Pp" else 0)
    try:
        return datetime(*numbers)  # type: ignore[arg-type]
    except ValueError:
        return None


def _first_plausible(
    patterns: list[re.Pattern[str]], text: str, latest: datetime, *, dashed: bool
) -> datetime | None:
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = _in_name(match)
            alone = dashed and not _GLUED.search(text, 0, match.start())
            earliest = EARLIEST_PLAUSIBLE if alone else FILENAME_EARLIEST
            if value is not None and earliest <= value < latest:
                return value
    return None


def _epoch_from_filename(name: str) -> datetime | None:
    """Timezone-aware (UTC) moment for names that carry a Unix timestamp in milliseconds."""
    match = _FILENAME_EPOCH_MS.search(name)
    if not match:
        return None
    seconds = int(match.group(1)) // 1000  # whole seconds, like every other source
    return datetime.fromtimestamp(seconds, UTC)


def date_from_filename(filename: str, latest: datetime = FILENAME_LATEST) -> datetime | None:
    """Local wall-clock date from a file name (timestamps in names are given as UTC): the
    first believable one before ``latest``. Believable is from ``EARLIEST_PLAUSIBLE`` for a
    dashed date standing alone, from ``FILENAME_EARLIEST`` for every other spelling."""
    name = PurePath(filename).stem
    found = _first_plausible(_COMPACT_DATETIMES, name, latest, dashed=False)
    if found is None:
        found = _first_plausible(_DASHED_DATETIMES, name, latest, dashed=True)
    if found is not None:
        return found
    epoch = _epoch_from_filename(name)
    if epoch is not None:
        return epoch.replace(tzinfo=None)
    return _first_plausible(_DASHED_DATES, name, latest, dashed=True) or _first_plausible(
        _COMPACT_DATES, name, latest, dashed=False
    )


def _plausible(value: datetime, now: datetime) -> bool:
    return EARLIEST_PLAUSIBLE <= value <= now.replace(tzinfo=None) + FUTURE_TOLERANCE


def pick_capture_time(
    dates: MetadataDates, *, filename: str, file_mtime: datetime, now: datetime
) -> CaptureTime:
    """Apply the fallback chain.

    ``file_mtime`` must be timezone-aware *in the zone the file was saved in* (the adapter
    gives the machine's local zone); ``now`` must be timezone-aware."""
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

    epoch = _epoch_from_filename(PurePath(filename).stem)
    if epoch is not None and _plausible(epoch.replace(tzinfo=None), now):
        return _in_zone_of(epoch, file_mtime, DateSource.FILENAME)
    not_after = min(now.replace(tzinfo=None) + FUTURE_TOLERANCE, FILENAME_LATEST)
    from_name = date_from_filename(filename, not_after)
    if from_name and _plausible(from_name, now):
        return CaptureTime(from_name, None, DateSource.FILENAME)

    return _from_mtime(file_mtime, now)


def _in_zone_of(moment: datetime, reference: datetime, source: DateSource) -> CaptureTime:
    """Express an absolute moment as wall-clock time in the reference's zone (the machine's
    local zone): a photo saved at 00:30 on 1 January must not land in December."""
    local = moment.astimezone(reference.tzinfo)
    offset = local.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else None
    # whole seconds, like every other source (an mtime has nanoseconds; QA A12)
    wall = max(local.replace(tzinfo=None, microsecond=0), EARLIEST_PLAUSIBLE)
    return CaptureTime(wall, minutes, source)


def _from_mtime(file_mtime: datetime, now: datetime) -> CaptureTime:
    return _in_zone_of(min(file_mtime, now), file_mtime, DateSource.FILE_MTIME)
