"""Composition root: the one place that picks real adapters and wires them together."""

from dataclasses import dataclass

from photo_assistant.adapters.exiftool_reader import ExifToolReader, ExifToolStripper
from photo_assistant.adapters.filesystem import (
    Blake3Hasher,
    DiskLibraryStore,
    FolderSourceReader,
    SystemClock,
)
from photo_assistant.adapters.passwords import Argon2Hasher
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.api.settings import Settings
from photo_assistant.app.accounts import Accounts
from photo_assistant.app.derivatives import GeneratePreview
from photo_assistant.app.downloads import Downloads
from photo_assistant.app.editing import Editor
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
    accounts: Accounts
    editor: Editor
    clock: SystemClock
    downloads: Downloads

    def close(self) -> None:
        self.worker.stop()
        self.exiftool.close()
        self.repo.close()


def build_services(settings: Settings) -> Services:
    root = settings.data_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    repo = SqliteRepository(open_database(root / "library.db", backup_dir=root / "db-backups"))
    store = DiskLibraryStore(root)
    store.sweep_tmp()
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
    hasher = Argon2Hasher(settings.argon2_time_cost, settings.argon2_memory_kib)
    accounts = Accounts(repo, hasher, clock)
    editor = Editor(
        repo,
        store,
        renderer,
        thumb_edge=settings.thumb_edge,
        preview_edge=settings.preview_edge,
    )
    downloads = Downloads(store, renderer, ExifToolStripper(), root / "tmp")
    return Services(
        settings, repo, store, importer, worker, exiftool, accounts, editor, clock, downloads
    )
