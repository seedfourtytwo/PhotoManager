"""Composition root: the one place that picks real adapters and wires them together."""

from dataclasses import dataclass
from pathlib import Path

from photo_assistant.adapters.exiftool_reader import ExifToolReader
from photo_assistant.adapters.filesystem import (
    Blake3Hasher,
    DiskLibraryStore,
    FolderSourceReader,
    SystemClock,
)
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.api.settings import Settings
from photo_assistant.app.derivatives import GeneratePreview
from photo_assistant.app.import_source import PREVIEW_JOB, ImportSettings, ImportSource
from photo_assistant.app.worker import Worker

SCAN_JOB = "scan_source"


@dataclass
class Services:
    settings: Settings
    repo: SqliteRepository
    store: DiskLibraryStore
    importer: ImportSource
    worker: Worker
    exiftool: ExifToolReader

    def close(self) -> None:
        self.worker.stop()
        self.exiftool.close()
        self.repo.close()


def build_services(settings: Settings) -> Services:
    root = settings.data_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    repo = SqliteRepository(open_database(root / "library.db", backup_dir=root / "db-backups"))
    repo.recover_interrupted_jobs()
    store = DiskLibraryStore(root)
    renderer = VipsRenderer(concurrency=settings.vips_concurrency)
    exiftool = ExifToolReader()
    clock = SystemClock()
    importer = ImportSource(
        repo=repo,
        reader=FolderSourceReader(),
        hasher=Blake3Hasher(),
        metadata=exiftool,
        renderer=renderer,
        store=store,
        clock=clock,
        settings=ImportSettings(
            min_free_bytes=int(settings.min_free_gb * 1000**3), thumb_edge=settings.thumb_edge
        ),
    )
    worker = Worker(
        repo,
        {
            PREVIEW_JOB: GeneratePreview(repo, store, renderer, settings.preview_edge),
            SCAN_JOB: lambda payload: importer.run(int(str(payload["source_id"]))),
        },
        clock,
        poll_seconds=settings.worker_poll_seconds,
    )
    return Services(settings, repo, store, importer, worker, exiftool)


def overlaps(a: Path, b: Path) -> bool:
    """True if either folder contains the other (or they are the same)."""
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents
