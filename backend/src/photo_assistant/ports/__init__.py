"""Protocol interfaces the app layer depends on. Adapters implement them; tests fake them."""

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

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


class ImageRenderer(Protocol):
    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        """Write an orientation-corrected WebP fitting a square box. Returns its size."""
        ...


@dataclass(frozen=True, slots=True)
class SourceFile:
    relative_path: str  # posix, relative to the source root
    absolute_path: Path
    byte_size: int
    mtime: datetime  # timezone-aware


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


class Repository(Protocol):
    # sources
    def add_source(self, label: str, root: str) -> Source: ...
    def get_source(self, source_id: int) -> Source | None: ...
    def list_sources(self) -> list[Source]: ...
    def set_source_enabled(self, source_id: int, enabled: bool) -> None: ...

    # assets
    def find_asset_id_by_hash(self, content_hash: str) -> int | None: ...
    def add_asset(self, asset: NewAsset, imported_at: datetime) -> int: ...
    def record_import(
        self,
        asset: NewAsset,
        imported_at: datetime,
        source_id: int,
        relative_path: str,
        thumb: RenderedImage,
        job_kind: str,
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
    def add_asset_source(self, asset_id: int, source_id: int, relative_path: str) -> None: ...
    def asset_id_for_source_path(self, source_id: int, relative_path: str) -> int | None: ...
    def origins_of(self, asset_id: int) -> list[tuple[Source, str]]: ...

    # import runs
    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int: ...
    def get_import_report(self, run_id: int) -> ImportReport | None: ...
    def list_import_runs(self, source_id: int | None = None) -> list[dict[str, object]]: ...

    # job queue
    def enqueue(self, kind: str, payload: dict[str, object]) -> int: ...
    def claim_next_job(self, now: datetime) -> Job | None: ...
    def complete_job(self, job_id: int) -> None: ...
    def fail_job(self, job_id: int, error: str, retry: bool) -> None: ...
    def list_jobs(self, status: str | None = None) -> list[dict[str, object]]: ...
    def retry_job(self, job_id: int) -> bool: ...
    def job_counts(self) -> dict[str, int]: ...
