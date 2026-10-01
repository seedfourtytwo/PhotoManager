"""SyncSource: bring a source up to date — pull it first if it is remote, then import it.

A remote source (``kind = "rclone"``, ``config_json = {"remote", "path"}``) is a folder source
whose root is ``<data>/staging/<source_id>``: rclone mirrors the remote there (read-only on the
remote), then the ordinary ImportSource imports that folder. Any other source is just imported,
so this is safe to use as the handler for every "scan source" job.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.app.import_source import SourceUnavailableError
from photo_assistant.domain.model import ImportReport, RunStatus, Source
from photo_assistant.domain.remote_source import RemoteConfig, RemoteConfigError
from photo_assistant.ports import Clock
from photo_assistant.ports.sync import (
    RemoteSourceStore,
    SourceSync,
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
    SyncReport,
)

log = logging.getLogger(__name__)

SCAN_JOB_KIND = "scan_source"  # the job kind api.services registers (SCAN_JOB)
# Retrying these at once can't help (and hammering a throttling provider makes it worse):
# record them for the user and finish the job.
_FINAL = (SyncAuthError, SyncNotFoundError, SyncRateLimitedError)


class SourceLookup(Protocol):
    def get_source(self, source_id: int) -> Source | None: ...


class Importer(Protocol):
    def run(self, source_id: int) -> tuple[int, ImportReport]: ...


class ReportSink(Protocol):
    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int: ...


class RemoteLister(Protocol):
    def list_remotes(self) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    run_id: int
    report: ImportReport | None  # None when the pull failed and nothing was imported
    sync: SyncReport | None  # None for sources that are not remote


def add_remote_source(
    store: RemoteSourceStore,
    remotes: RemoteLister,
    staging_root: Path,
    label: str,
    settings: Mapping[str, object],
) -> int:
    """Validate and register a remote source. Raises RemoteConfigError with a fix-it message."""
    config = RemoteConfig.from_mapping(settings)
    if config.remote not in remotes.list_remotes():
        raise RemoteConfigError(
            f"no remote called '{config.remote}' on this machine: create it first with "
            "'rclone config' (see the cloud sources guide)"
        )
    return store.add_remote_source(label, config, staging_root)


class SyncSource:
    def __init__(
        self,
        *,
        sources: SourceLookup,
        remotes: RemoteSourceStore,
        sync: SourceSync,
        importer: Importer,
        reports: ReportSink,
        clock: Clock,
        staging_root: Path,
        options: SyncOptions,
    ) -> None:
        self._sources = sources
        self._remotes = remotes
        self._sync = sync
        self._importer = importer
        self._reports = reports
        self._clock = clock
        self._staging_root = staging_root
        self._options = options

    def run(self, source_id: int) -> SyncOutcome:
        source = self._sources.get_source(source_id)
        if source is None or not source.enabled:
            raise SourceUnavailableError(f"source {source_id} is missing or disabled")
        started = self._clock.now()
        try:
            config = self._remotes.remote_config(source_id)
        except RemoteConfigError as exc:
            return self._record_failure(source, started, exc)
        if config is None:
            return self._import(source_id, None)
        staging = self._staging_root / str(source_id)
        self._remotes.set_root(source_id, str(staging))  # follows a moved data root
        try:
            pulled = self._sync.pull(config, staging, self._options)
        except _FINAL as exc:
            return self._record_failure(source, started, exc)
        except SyncError as exc:
            self._record_failure(source, started, exc)
            raise
        if pulled.partial:
            log.warning(
                "remote pull incomplete",
                extra={"source_id": source_id, "errors": pulled.errors},
            )
        return self._import(source_id, pulled)

    def _import(self, source_id: int, pulled: SyncReport | None) -> SyncOutcome:
        run_id, report = self._importer.run(source_id)
        return SyncOutcome(run_id, report, pulled)

    def _record_failure(self, source: Source, started: datetime, exc: Exception) -> SyncOutcome:
        """Put the failure where the user looks: the source's import history."""
        report = ImportReport(
            source_id=source.id,
            status=RunStatus.FAILED,
            message=f"Could not pull '{source.label}': {exc}",
        )
        log.warning("remote pull failed", extra={"source_id": source.id, "error": str(exc)})
        run_id = self._reports.save_import_report(report, started, self._clock.now())
        return SyncOutcome(run_id, None, None)
