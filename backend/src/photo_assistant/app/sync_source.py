"""SyncSource: bring a source up to date — pull it first if it is remote, then import it.

A remote source (``kind`` "rclone" or "proton", its settings in ``config_json``) is a folder
source whose root is ``<data>/staging/<source_id>``: the provider's tool mirrors the remote
there (read-only on the remote), then the ordinary ImportSource imports that folder. Any other
source is just imported, so this is safe to use as the handler for every "scan source" job.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.app.import_source import SourceUnavailableError
from photo_assistant.domain.access import KEPT_KIND
from photo_assistant.domain.model import ImportReport, RunStatus, Source
from photo_assistant.domain.remote_source import (
    PROTON_PHOTOS,
    RemoteConfig,
    RemoteConfigError,
    proton_folder_name_problem,
)
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
    SyncUnsupportedError,
)

log = logging.getLogger(__name__)

SCAN_JOB_KIND = "scan_source"  # the job kind api.services registers for every source kind
# Recorded for the user in the source's import history, and the job ends there: signing in
# or naming another folder is theirs to do, and a throttling provider is asked again at the
# source's next check, not sooner.
_FINAL = (SyncAuthError, SyncNotFoundError, SyncRateLimitedError)
_SHOWN_ERRORS = 3  # of a partial pull, in the import's message; the log has the count


def partial_pull_message(label: str, pulled: SyncReport) -> str:
    """What the import's entry says when the pull before it brought only part of the remote."""
    count = pulled.errors
    text = (
        f"{count} file{'' if count == 1 else 's'} could not be downloaded from '{label}' "
        "(what did arrive was imported)"
    )
    shown = pulled.error_messages[:_SHOWN_ERRORS]
    if shown:
        text += ": " + "; ".join(shown)
    if shown and count > len(shown):
        text += f"; and {count - len(shown)} more"
    return text


class SourceLookup(Protocol):
    def get_source(self, source_id: int) -> Source | None: ...


class Importer(Protocol):
    def run(self, source_id: int) -> tuple[int, ImportReport]: ...


class ReportSink(Protocol):
    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int: ...

    def set_import_run_message(self, run_id: int, message: str) -> None: ...


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
    owner_id: int,
) -> int:
    """Validate and register a remote source, owned by the admin adding it. Raises
    RemoteConfigError with a fix-it message."""
    config = RemoteConfig.from_mapping(settings)
    if config.remote not in remotes.list_remotes():
        raise RemoteConfigError(
            f"no remote called '{config.remote}' on this machine: create it first with "
            "'rclone config' (see the cloud sources guide)"
        )
    return store.add_remote_source(label, config, staging_root, owner_id)


class ProtonAccount(Protocol):
    def check(self) -> None: ...

    def folders(self, path: str) -> list[str]: ...

    def create_folder(self, parent: str, name: str) -> str: ...


def add_proton_source(
    store: RemoteSourceStore,
    account: ProtonAccount,
    staging_root: Path,
    label: str,
    path: str,
    owner_id: int,
) -> int:
    """Register a Proton Drive source for a place that exists, owned by the admin adding it.
    Raises RemoteConfigError for a place that may not be read, SyncError subclasses when
    Proton can't confirm it."""
    config = RemoteConfig.proton(path)
    if path == PROTON_PHOTOS:
        account.check()
    else:
        account.folders(path)
    return store.add_remote_source(label, config, staging_root, owner_id)


def create_proton_folder(account: ProtonAccount, parent: str, name: str) -> str:
    """Make a new folder in My files (a place for a backup copy); its path. Raises
    RemoteConfigError for a bad place or name, SyncError subclasses when Proton can't."""
    if parent == PROTON_PHOTOS:
        raise RemoteConfigError("folders can only be made in My files")
    RemoteConfig.proton(parent)
    if problem := proton_folder_name_problem(name):
        raise RemoteConfigError(problem)
    if name in account.folders(parent):
        raise RemoteConfigError(f"'{name}' already exists there")
    return account.create_folder(parent, name)


class ProviderSync:
    """One SourceSync over several: each remote is pulled by its provider's tool."""

    def __init__(self, by_provider: Mapping[str, SourceSync]) -> None:
        self._by_provider = by_provider

    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        sync = self._by_provider.get(remote.provider)
        if sync is None:
            raise SyncUnsupportedError(f"this version cannot pull from '{remote.provider}'")
        return sync.pull(remote, staging, options)


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
        if source is not None and source.kind == KEPT_KIND:
            raise SourceUnavailableError(f"source '{source.label}' is no longer watched")
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
        outcome = self._import(source_id, pulled)
        if pulled.partial and outcome.report is not None:
            log.warning(
                "remote pull incomplete",
                extra={"source_id": source_id, "errors": pulled.errors},
            )
            # on the import's own entry, whose status stays what the import made it: an entry
            # of its own read as "last import failed" above the import of what did arrive
            note = partial_pull_message(source.label, pulled)
            report = outcome.report
            report.message = f"{report.message} {note}" if report.message else note
            self._reports.set_import_run_message(outcome.run_id, report.message)
        return outcome

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
