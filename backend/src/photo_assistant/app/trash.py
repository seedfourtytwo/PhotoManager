"""Trash (FEATURES 11.3): deleting only hides; purging removes the *library copy*.

Sources are never touched: a purged photo that is still in a source is remembered by its
content hash, so rescans report it as skipped instead of importing it again.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol

from photo_assistant.domain.model import Asset
from photo_assistant.ports import Clock

TRASH_DAYS = 30
PURGE_JOB = "purge_trash"


class TrashStore(Protocol):
    def trash_assets(self, ids: Sequence[int], user_id: int, now: datetime) -> int: ...
    def restore_assets(self, ids: Sequence[int]) -> int: ...
    def purge_candidates(
        self, ids: Sequence[int] | None, trashed_before: datetime | None
    ) -> list[Asset]: ...
    def purge_asset(self, asset: Asset, now: datetime) -> None: ...


class LibraryFiles(Protocol):
    def remove(self, relative_path: str) -> None:
        """Delete a library original or derivative (never anything else)."""
        ...

    def remove_edited(self, content_hash: str) -> None: ...


class Trash:
    def __init__(self, repo: TrashStore, files: LibraryFiles, clock: Clock) -> None:
        self._repo = repo
        self._files = files
        self._clock = clock

    def trash(self, ids: Sequence[int], user_id: int) -> int:
        return self._repo.trash_assets(ids, user_id, self._clock.now())

    def restore(self, ids: Sequence[int]) -> int:
        return self._repo.restore_assets(ids)

    def empty(self, ids: Sequence[int] | None) -> int:
        """Purge these photos from the trash (all of it when ``ids`` is None)."""
        return self._purge(self._repo.purge_candidates(ids, None))

    def purge_expired(self, payload: dict[str, object]) -> int:
        cutoff = self._clock.now() - timedelta(days=TRASH_DAYS)
        return self._purge(self._repo.purge_candidates(None, cutoff))

    def _purge(self, assets: list[Asset]) -> int:
        for asset in assets:
            # Files first: if this stops half-way, the photo is still in the trash and a
            # second purge finishes the job.
            for relative in (asset.library_path, asset.thumb_path, asset.preview_path):
                if relative:
                    self._files.remove(relative)
            self._files.remove_edited(asset.content_hash)
            self._repo.purge_asset(asset, self._clock.now())
        return len(assets)
