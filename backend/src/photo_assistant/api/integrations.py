"""Composition of the integrations (uploads, device tokens, remote sources, AI).

The integrator calls ``build_integrations`` from ``api/services.py`` and stores the result on
``app.state.integrations``; see docs/wiring/ai-sources.md for the exact steps.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from photo_assistant.adapters.filesystem import SystemClock
from photo_assistant.adapters.ollama_ai import build_ai_provider
from photo_assistant.adapters.rclone_sync import RcloneSync
from photo_assistant.adapters.source_area_store import SourceAreaStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_integrations import (
    SqliteAILog,
    SqliteDevices,
    SqliteInboxes,
    SqliteRemoteSources,
)
from photo_assistant.adapters.upload_spool import DiskUploadSpool
from photo_assistant.api.settings import IntegrationSettings
from photo_assistant.app.devices import DeviceTokens
from photo_assistant.app.sync_source import Importer, SyncSource
from photo_assistant.app.upload import UploadInbox, UploadSettings
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
    sync_source: SyncSource
    staging_root: Path
    ai: AIProvider
    ai_log: SqliteAILog


def build_integrations(
    *,
    data_root: Path,
    settings: IntegrationSettings,
    conn: Database | sqlite3.Connection,
    repo: Repository,
    importer: Importer,
    clock: Clock | None = None,
) -> Integrations:
    clock = clock or SystemClock()
    remote_sources = SqliteRemoteSources(conn, repo)
    rclone = RcloneSync(settings.rclone_binary, settings.rclone_config)
    ai_log = SqliteAILog(conn)
    upload = UploadInbox(
        inbox=SqliteInboxes(conn, repo),
        library=repo,
        spool=DiskUploadSpool(data_root / "tmp"),
        clock=clock,
        inbox_root=inbox_root(data_root),
        settings=UploadSettings(max_bytes=settings.upload_max_bytes),
    )
    sync_source = SyncSource(
        sources=repo,
        remotes=remote_sources,
        sync=rclone,
        importer=importer,
        reports=repo,
        clock=clock,
        staging_root=staging_root(data_root),
        options=settings.sync_options(),
    )
    return Integrations(
        repo=repo,
        upload=upload,
        upload_max_files=settings.upload_max_files,
        devices=DeviceTokens(SqliteDevices(conn), clock),
        remote_sources=remote_sources,
        rclone=rclone,
        sync_source=sync_source,
        staging_root=staging_root(data_root),
        ai=build_ai_provider(settings.ollama(), ai_log),
        ai_log=ai_log,
    )


def get_integrations(request: Request) -> Integrations:
    integrations: Integrations = request.app.state.integrations
    return integrations


IntegrationsDep = Annotated[Integrations, Depends(get_integrations)]
