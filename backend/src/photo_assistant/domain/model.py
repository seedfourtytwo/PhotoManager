"""Core value types shared by every layer. Pure data, no behaviour that needs I/O."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from photo_assistant.domain.capture_time import DateSource, MetadataDates
from photo_assistant.domain.exposure import NO_EXPOSURE, Exposure
from photo_assistant.domain.media_types import MediaKind
from photo_assistant.domain.recheck import Recheck

# Ids are SQLite integers: anything larger can name nothing (QA A11: it used to be a 500).
MAX_ID = 2**63 - 1


@dataclass(frozen=True, slots=True)
class PhotoMetadata:
    """What an adapter could read from one file. Everything optional: files are messy."""

    dates: MetadataDates = field(default_factory=MetadataDates)
    width: int | None = None
    height: int | None = None
    orientation: int | None = None  # EXIF 1..8; 5-8 swap width and height when displayed
    latitude: float | None = None
    longitude: float | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    mime_type: str | None = None
    live_photo_id: str | None = None  # Apple ContentIdentifier, pairs a photo with its video
    error: str | None = None  # set when the file could not be read as an image
    exposure: Exposure = NO_EXPOSURE

    @property
    def display_size(self) -> tuple[int, int] | None:
        if self.width is None or self.height is None:
            return None
        if self.orientation in (5, 6, 7, 8):
            return self.height, self.width
        return self.width, self.height


@dataclass(frozen=True, slots=True)
class Source:
    id: int
    label: str
    root: str  # absolute path on this machine; sources are external, the library is portable
    enabled: bool = True
    kind: str = "folder"
    owner_id: int | None = None
    recheck: Recheck = Recheck.OFF  # checks itself again on a timer; off = only when asked


@dataclass(frozen=True, slots=True)
class NewAsset:
    content_hash: str
    kind: MediaKind
    mime_type: str | None
    byte_size: int
    width: int | None
    height: int | None
    taken_at: datetime
    tz_offset_minutes: int | None
    date_source: DateSource
    latitude: float | None
    longitude: float | None
    camera_make: str | None
    camera_model: str | None
    orientation: int | None
    library_path: str  # relative to the data root
    exposure: Exposure = NO_EXPOSURE


@dataclass(frozen=True, slots=True)
class Asset(NewAsset):
    id: int = 0
    imported_at: datetime = datetime(1970, 1, 1)
    thumb_path: str | None = None
    preview_path: str | None = None
    variant_of: int | None = None  # e.g. an iPhone IMG_E edit points at its original
    thumb_size: tuple[int, int] | None = None  # unknown for photos migrated from M1
    colour: str | None = None  # dominant colour "#rrggbb" (domain/colour.py); None: not yet


class Outcome(StrEnum):
    IMPORTED = "imported"
    DUPLICATE = "duplicate"  # same content already in the library (from any source)
    ALREADY_KNOWN = "already_known"  # this exact source file was imported before
    SKIPPED = "skipped"  # recognised but not supported (yet): videos, PDFs, …
    FAILED = "failed"  # should have worked but didn't: corrupt, unreadable, empty


# The order a report lists its files in: what needs a look first, so that the failures of a
# rescan never hide behind thousands of files that were seen before.
REPORT_ORDER = (
    Outcome.FAILED,
    Outcome.SKIPPED,
    Outcome.DUPLICATE,
    Outcome.ALREADY_KNOWN,
    Outcome.IMPORTED,
)


@dataclass(frozen=True, slots=True)
class ItemResult:
    relative_path: str  # relative to the source root
    outcome: Outcome
    reason: str | None = None
    asset_id: int | None = None


class RunStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    PAUSED_LOW_DISK = "paused_low_disk"
    FAILED = "failed"


@dataclass(slots=True)
class ImportReport:
    source_id: int
    status: RunStatus = RunStatus.RUNNING
    items: list[ItemResult] = field(default_factory=list)
    ignored: int = 0  # sidecars and OS clutter, not listed individually
    message: str | None = None

    def add(self, item: ItemResult) -> None:
        self.items.append(item)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for i in self.items if i.outcome is outcome)

    @property
    def files_seen(self) -> int:
        return len(self.items) + self.ignored

    def summary(self) -> dict[str, int]:
        counts = {o.value: self.count(o) for o in Outcome}
        counts["ignored"] = self.ignored
        counts["files_seen"] = self.files_seen
        return counts
