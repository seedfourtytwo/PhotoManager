"""Composition of the integrations (uploads, device tokens, remote sources, AI).

``api/services.py`` calls ``build_integrations`` and keeps the result as
``Services.integrations``; routes reach it through ``api/deps.py``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from photo_assistant.adapters.ollama_ai import build_ai_provider
from photo_assistant.adapters.proton_drive import ProtonDrive, find_binary
from photo_assistant.adapters.rclone_sync import RcloneSync
from photo_assistant.adapters.source_area_store import SourceAreaStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_integrations import (
    SqliteAILog,
    SqliteDevices,
    SqliteInboxes,
    SqliteRemoteSources,
)
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.adapters.upload_spool import DiskUploadSpool
from photo_assistant.api.settings import IntegrationSettings
from photo_assistant.app.ai_captions import CAPTION_JOB, CaptionPhotos
from photo_assistant.app.album_plans import PLAN_JOB, AlbumPlanner
from photo_assistant.app.devices import DeviceTokens
from photo_assistant.app.sync_source import Importer, ProviderSync, SyncSource
from photo_assistant.app.upload import UploadInbox, UploadSettings
from photo_assistant.domain.remote_source import PROTON, RCLONE
from photo_assistant.ports import Clock, LibraryStore, Repository
from photo_assistant.ports.ai import AIProvider


def staging_root(data_root: Path) -> Path:
    return data_root / "staging"


def inbox_root(data_root: Path) -> Path:
    return data_root / "inbox"


def with_source_areas(store: LibraryStore, data_root: Path) -> SourceAreaStore:
    """The store to give the importer, so staging and inbox folders can be imported."""
    return SourceAreaStore(store, [staging_root(data_root), inbox_root(data_root)])


@dataclass
class Integrations:
    repo: Repository
    upload: UploadInbox
    upload_max_files: int
    devices: DeviceTokens
    remote_sources: SqliteRemoteSources
    rclone: RcloneSync
    proton: ProtonDrive
    sync_source: SyncSource
    staging_root: Path
    ai: AIProvider
    ai_log: SqliteAILog
    planner: AlbumPlanner  # suggested albums with their AI titles (plain ones with the AI off)
    # the AI's background jobs, each on a worker thread of its own; none with the AI off
    ai_jobs: dict[str, Callable[[dict[str, object]], object]] = field(default_factory=dict)


def build_integrations(
    *,
    data_root: Path,
    settings: IntegrationSettings,
    db: Database,
    repo: SqliteRepository,  # the AI jobs read and keep captions and plans in it too
    importer: Importer,
    clock: Clock,
    absolute: Callable[[str], Path],
    min_free_bytes: int = 0,
) -> Integrations:
    """``db``: the process's one Database, which these stores share with ``repo``.
    ``absolute``: a library path on disk (the AI reads the photos' previews)."""
    remote_sources = SqliteRemoteSources(db, repo)
    rclone = RcloneSync(settings.rclone_binary, settings.rclone_config)
    proton = ProtonDrive(find_binary(settings.proton_drive_binary))
    ai_log = SqliteAILog(db)
    upload = UploadInbox(
        inbox=SqliteInboxes(db, repo),
        library=repo,
        spool=DiskUploadSpool(data_root / "tmp"),
        clock=clock,
        inbox_root=inbox_root(data_root),
        settings=UploadSettings(max_bytes=settings.upload_max_bytes, min_free_bytes=min_free_bytes),
    )
    sync_source = SyncSource(
        sources=repo,
        remotes=remote_sources,
        sync=ProviderSync({RCLONE: rclone, PROTON: proton}),
        importer=importer,
        reports=repo,
        clock=clock,
        staging_root=staging_root(data_root),
        options=settings.sync_options(),
    )
    ollama = settings.ollama()
    ai = build_ai_provider(ollama, ai_log)
    caption_model = ollama.caption_model if ollama else None
    plan_model = ollama.plan_model if ollama else None
    captions = CaptionPhotos(repo, ai, caption_model, absolute) if caption_model else None
    planner = AlbumPlanner(repo, ai, plan_model, captions)
    ai_jobs: dict[str, Callable[[dict[str, object]], object]] = {}
    if captions:
        ai_jobs[CAPTION_JOB] = captions
    if plan_model:
        ai_jobs[PLAN_JOB] = planner
    return Integrations(
        repo=repo,
        upload=upload,
        upload_max_files=settings.upload_max_files,
        devices=DeviceTokens(SqliteDevices(db), clock),
        remote_sources=remote_sources,
        rclone=rclone,
        proton=proton,
        sync_source=sync_source,
        staging_root=staging_root(data_root),
        ai=ai,
        ai_log=ai_log,
        planner=planner,
        ai_jobs=ai_jobs,
    )
