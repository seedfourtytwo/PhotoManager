"""Stop watching a folder: remove a source from the library (admin, Admin → Folders).

Only the library's own records change. The folder on disk (or in the cloud) is never read,
written, moved or deleted here; only a cloud source's staging copy, which is the app's own
pull under ``data/staging/<id>``, is deleted. Photos that another source also holds are not
touched. Those found *only* in this folder are either kept, or moved to the 30-day trash.

A kept photo has no source any more, so by the visibility rule (ARCHITECTURE §7) only admins
see it, plus the members of any album it is in. The web app says so before anyone confirms.
"""

import logging
from collections.abc import Collection, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.domain.access import INBOX_KIND
from photo_assistant.domain.errors import InvalidError, NotFoundError
from photo_assistant.domain.model import Source
from photo_assistant.domain.remote_source import PROTON, RCLONE
from photo_assistant.ports import Clock, ImportBusyError, SourceBusyError

log = logging.getLogger(__name__)

_STAGED_KINDS = (RCLONE, PROTON)  # pulled into data/staging/<id> before they are imported


class PhotosOnlyHere(StrEnum):
    """What happens to the photos no other source holds."""

    KEEP = "keep"
    TRASH = "trash"


class SourceNotFoundError(NotFoundError):
    """No source with that id."""


class InboxNotRemovableError(InvalidError):
    """An upload inbox belongs to its account; it goes when the account goes."""


@dataclass(frozen=True, slots=True)
class Removal:
    """What removing a source would do: its photos, and those no other source holds."""

    photos: int
    only_here: int


@dataclass(frozen=True, slots=True)
class Removed:
    only_here: int
    trashed: int


class SourceRemovalStore(Protocol):
    def get_source(self, source_id: int) -> Source | None: ...

    def source_holdings(self, source_id: int) -> dict[int, frozenset[int]]:
        """Each live photo in this source → every source that holds it."""
        ...

    def remove_source(
        self, source_id: int, *, check_kind: str, trash: Sequence[int], by: int, now: datetime
    ) -> int:
        """Atomically: trash those photos, forget the source; raises SourceBusyError while a
        check of it runs."""
        ...


class ImportLock(Protocol):
    def exclusive_import(self) -> AbstractContextManager[None]: ...


class StagingFolders(Protocol):
    def remove(self, source_id: int) -> None:
        """Delete the app's own pulled copy of a cloud source (nothing else)."""
        ...


def only_from(source_id: int, holdings: Mapping[int, Collection[int]]) -> list[int]:
    """The photos that no source but this one holds, smallest id first."""
    return sorted(a for a, holders in holdings.items() if set(holders) == {source_id})


class StopWatching:
    def __init__(
        self,
        repo: SourceRemovalStore,
        imports: ImportLock,
        staging: StagingFolders,
        clock: Clock,
    ) -> None:
        self._repo = repo
        self._imports = imports
        self._staging = staging
        self._clock = clock

    def preview(self, source_id: int) -> Removal:
        self._require(source_id)
        holdings = self._repo.source_holdings(source_id)
        return Removal(photos=len(holdings), only_here=len(only_from(source_id, holdings)))

    def stop(self, source_id: int, photos: PhotosOnlyHere, admin_id: int) -> Removed:
        source = self._require(source_id)
        if source.kind == INBOX_KIND:
            raise InboxNotRemovableError(
                "an upload inbox belongs to its account and cannot be removed"
            )
        # Holding the import lock: no import can link a photo to another source between
        # deciding which photos are found only here and removing the source.
        try:
            with self._imports.exclusive_import():
                only_here = only_from(source_id, self._repo.source_holdings(source_id))
                trashed = self._repo.remove_source(
                    source_id,
                    check_kind=SCAN_JOB_KIND,
                    trash=only_here if photos is PhotosOnlyHere.TRASH else [],
                    by=admin_id,
                    now=self._clock.now(),
                )
        except ImportBusyError as exc:
            raise SourceBusyError(
                "an import is running; try again when it is done (Admin shows its progress)"
            ) from exc
        if source.kind in _STAGED_KINDS:
            self._remove_staging(source)
        log.info(
            "source removed",
            extra={"source_id": source_id, "only_here": len(only_here), "trashed": trashed},
        )
        return Removed(only_here=len(only_here), trashed=trashed)

    def _require(self, source_id: int) -> Source:
        source = self._repo.get_source(source_id)
        if source is None:
            raise SourceNotFoundError("source not found")
        return source

    def _remove_staging(self, source: Source) -> None:
        """The source is gone already: a copy left behind only takes disk space, so it is
        logged for the admin rather than failing the request."""
        try:
            self._staging.remove(source.id)
        except OSError as exc:
            log.warning(
                "could not delete a removed cloud source's staging copy",
                extra={"source_id": source.id, "reason": exc.strerror or str(exc)},
            )
