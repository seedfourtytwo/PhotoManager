"""Protocol interfaces the app layer depends on. Adapters implement them; tests fake them."""

from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.access import SourceAccess, Viewer
from photo_assistant.domain.edit_recipe import Recipe
from photo_assistant.domain.model import (
    Asset,
    ImportReport,
    NewAsset,
    PhotoMetadata,
    Source,
)


class ImportBusyError(RuntimeError):
    """Another import into the same library is running (another process or thread)."""


class DuplicateAssetError(ValueError):
    """Content already in the library; ``asset_id`` is the existing photo."""

    def __init__(self, asset_id: int) -> None:
        super().__init__(f"content already in the library as asset {asset_id}")
        self.asset_id = asset_id


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware current time."""
        ...


class Hasher(Protocol):
    def hash_file(self, path: Path) -> str:
        """Lowercase hex BLAKE3 of the file, streamed."""
        ...


class MetadataReader(Protocol):
    def read_many(self, paths: Sequence[Path]) -> list[PhotoMetadata]:
        """One result per path, same order. Never raises for a bad file: sets ``error``."""
        ...


@dataclass(frozen=True, slots=True)
class RenderedImage:
    relative_path: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RenderSpec:
    """How to render a photo: its edit recipe, size, format and metadata."""

    recipe: Recipe | None = None
    max_edge: int | None = None  # fit the long edge; never upscale
    format: str = "webp"  # webp | jpeg | png
    quality: int = 80
    keep_metadata: bool = False  # EXIF/XMP carried over (orientation reset); else stripped


class ImageRenderer(Protocol):
    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        """Write an orientation-corrected WebP fitting a square box. Returns its size."""
        ...

    def render_pair(
        self,
        source: Path,
        big: Path,
        big_edge: int,
        small: Path,
        small_edge: int,
        recipe: Recipe | None = None,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Two WebP sizes (preview and thumbnail) from one decode, the recipe applied;
        returns both sizes."""
        ...

    def dimensions(self, image: Path) -> tuple[int, int]:
        """Width and height of an image file, as stored (no orientation applied)."""
        ...

    def render_variant(self, source: Path, destination: Path, spec: RenderSpec) -> tuple[int, int]:
        """Orientation-corrected, recipe applied, resized, encoded as asked. Returns its size."""
        ...


class MetadataStripper(Protocol):
    def strip(self, path: Path, *, location_only: bool) -> None:
        """Remove location (GPS) tags, or all metadata, from a file *in place*. Only ever
        called on temporary copies, never on library originals or source files."""
        ...


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """Cheap change detector for a source file: if both match, the content is unchanged."""

    byte_size: int
    mtime_ns: int
    ctime_ns: int = 0  # inode change time: tools can restore mtime, never ctime


@dataclass(frozen=True, slots=True)
class SourceFile:
    relative_path: str  # posix, relative to the source root
    absolute_path: Path
    byte_size: int
    mtime: datetime  # timezone-aware, local wall-clock zone
    mtime_ns: int = 0
    ctime_ns: int = 0

    @property
    def fingerprint(self) -> Fingerprint:
        return Fingerprint(self.byte_size, self.mtime_ns, self.ctime_ns)


class SourceReader(Protocol):
    def walk(self, source: Source) -> Iterator[SourceFile]:
        """Every regular file under the source root, in a stable order. Read-only."""
        ...


class LibraryStore(Protocol):
    """The data root on disk: originals, derivatives. Paths in and out are relative."""

    def store_original(self, source_file: Path, relative_path: str, content_hash: str) -> None:
        """Copy (never move) into the library; verify the hash; atomic. Idempotent."""
        ...

    def absolute(self, relative_path: str) -> Path: ...

    def free_bytes(self) -> int: ...

    def overlaps(self, folder: Path) -> bool:
        """True if the folder contains the library or is inside it."""
        ...

    def exclusive_import(self) -> AbstractContextManager[None]:
        """Hold the library's import lock; raise ImportBusyError if someone else has it."""
        ...


@dataclass(frozen=True, slots=True)
class Page:
    items: list[Asset]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    kind: str
    payload: dict[str, object]
    attempts: int


IMPORT_RUNS_LISTED = 200  # the import history shows the newest runs, not every rescan ever


class SourceRegistry(Protocol):
    def add_source(
        self,
        label: str,
        root: str | Callable[[int], str],
        owner_id: int | None = None,
        *,
        kind: str = "folder",
        access: SourceAccess | None = None,
        config: Mapping[str, object] | None = None,
    ) -> Source:
        """The one way to create a source (any kind); access defaults to the domain rule.
        Raises ValueError if its folder is already a source, and an InvalidError if the owner
        or someone on the access list is not an account."""
        ...


class Repository(SourceRegistry, Protocol):
    # sources
    def get_source(self, source_id: int) -> Source | None: ...
    def list_sources(self) -> list[Source]: ...
    def set_source_enabled(self, source_id: int, enabled: bool) -> None: ...

    # assets
    def find_asset_id_by_hash(self, content_hash: str) -> int | None: ...
    def is_purged_hash(self, content_hash: str) -> bool:
        """True if this content was purged from the library (it must not come back)."""
        ...

    def hashes_present(self, viewer: Viewer, hashes: Sequence[str]) -> dict[str, int | None]:
        """See ``ports.upload.LibraryIndex``: what this viewer already has."""
        ...

    def add_asset(self, asset: NewAsset, imported_at: datetime) -> int: ...
    def record_import(
        self,
        asset: NewAsset,
        imported_at: datetime,
        source_id: int,
        relative_path: str,
        thumb: RenderedImage,
        job_kind: str,
        fingerprint: Fingerprint | None = None,
    ) -> int:
        """Asset + origin + thumbnail + follow-up job, all or nothing.

        Raises DuplicateAssetError if the content is already in the library."""
        ...

    def get_asset(self, asset_id: int) -> Asset | None: ...
    def list_assets(self, limit: int, cursor: str | None = None) -> Page: ...
    def count_assets(self) -> int: ...
    def set_thumbnail(self, asset_id: int, thumb: RenderedImage) -> None: ...
    def set_preview(self, asset_id: int, preview: RenderedImage) -> None: ...
    def set_variant_of(self, asset_id: int, original_id: int) -> None: ...

    # where each asset came from (one asset, many source files)
    def add_asset_source(
        self,
        asset_id: int,
        source_id: int,
        relative_path: str,
        fingerprint: Fingerprint | None = None,
    ) -> None: ...
    def fingerprint_of(
        self, source_id: int, relative_path: str
    ) -> tuple[int, Fingerprint | None] | None: ...
    def previous_path_in_source(
        self, asset_id: int, source_id: int, exclude: str
    ) -> str | None: ...
    def asset_id_for_source_path(self, source_id: int, relative_path: str) -> int | None: ...

    # import runs
    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int: ...
    def get_import_report(self, run_id: int) -> ImportReport | None: ...
    def list_import_runs(
        self, source_id: int | None = None, limit: int = IMPORT_RUNS_LISTED
    ) -> list[dict[str, object]]:
        """Newest first, at most ``limit``."""
        ...

    # job queue
    def enqueue(self, kind: str, payload: dict[str, object]) -> int: ...
    def enqueue_once(self, kind: str, payload: dict[str, object] | None = None) -> int | None:
        """Queue a payload-less job unless one of that kind is already waiting."""
        ...

    def claim_next_job(
        self,
        now: datetime,
        *,
        only: Collection[str] | None = None,
        excluding: Collection[str] = (),
    ) -> Job | None:
        """Atomically mark the oldest queued job running: only of the kinds in ``only`` (if
        given), never of a kind in ``excluding`` (job lanes, B24)."""
        ...

    def complete_job(self, job_id: int) -> None: ...
    def fail_job(self, job_id: int, error: str, retry: bool) -> None: ...
    def list_jobs(self, status: str | None = None) -> list[dict[str, object]]: ...
    def retry_job(self, job_id: int) -> bool: ...
    def release_job(self, job_id: int) -> None:
        """Put a claimed job back in the queue without counting the attempt."""
        ...

    def job_counts(self) -> dict[str, int]: ...
