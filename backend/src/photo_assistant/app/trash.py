"""Trash (FEATURES 11.3): deleting only hides; purging removes the *library copy*.

Sources are never touched: a purged photo that is still in a source is remembered by its
content hash, so rescans report it as skipped instead of importing it again.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.model import Asset
from photo_assistant.ports import Clock
from photo_assistant.ports.library import AssetView

log = logging.getLogger(__name__)

TRASH_DAYS = 30
PURGE_JOB = "purge_trash"


class TrashStore(Protocol):
    def trashed_views(self, viewer: Viewer) -> list[AssetView]: ...
    def trash_assets(self, ids: Sequence[int], user_id: int, now: datetime) -> int: ...
    def restore_assets(self, ids: Sequence[int]) -> int: ...
    def purge_candidates(
        self, ids: Sequence[int] | None, trashed_before: datetime | None
    ) -> list[Asset]: ...
    def purge_asset(self, asset: Asset, now: datetime) -> bool:
        """Atomically: if the photo is still in the trash, forget it (remember its hash)."""
        ...


class LibraryFiles(Protocol):
    def remove(self, relative_path: str) -> None:
        """Delete a library original or derivative (never anything else)."""
        ...

    def remove_renditions(self, content_hash: str) -> None:
        """Delete the photo's cached edited previews and print renditions."""
        ...


class Trash:
    def __init__(self, repo: TrashStore, files: LibraryFiles, clock: Clock) -> None:
        self._repo = repo
        self._files = files
        self._clock = clock

    def trash(self, ids: Sequence[int], user_id: int) -> int:
        return self._repo.trash_assets(ids, user_id, self._clock.now())

    def restore(self, ids: Sequence[int]) -> int:
        return self._repo.restore_assets(ids)

    def empty(self, viewer: Viewer, ids: Sequence[int] | None) -> int:
        """Purge these photos from the trash (all of it when ``ids`` is None), but only those
        the viewer can see in the trash: an admin never purges someone's private photo."""
        mine = [v.id for v in self._repo.trashed_views(viewer)]
        if ids is None:
            wanted = mine
        else:
            asked = set(ids)
            wanted = [i for i in mine if i in asked]
        return self._purge(self._repo.purge_candidates(wanted, None))

    def purge_expired(self, payload: dict[str, object]) -> int:
        cutoff = self._clock.now() - timedelta(days=TRASH_DAYS)
        return self._purge(self._repo.purge_candidates(None, cutoff))

    def _purge(self, assets: list[Asset]) -> int:
        purged = 0
        for asset in assets:
            # Claim first: one transaction re-checks that the photo is *still* in the trash
            # and removes its rows. A restore that landed in between wins, and its files are
            # never touched (QA A2). If this stops after the claim, the files are orphans in
            # originals/ (found by verify-library) — never a photo without its original.
            if not self._repo.purge_asset(asset, self._clock.now()):
                continue
            self._remove_files(asset)
            purged += 1
        return purged

    def _remove_files(self, asset: Asset) -> None:
        """One file that cannot be deleted (permissions, a disk error) is logged and left as
        an orphan: it never keeps the rest of the trash from being emptied."""
        for relative in (asset.library_path, asset.thumb_path, asset.preview_path):
            if relative:
                try:
                    self._files.remove(relative)
                except OSError as exc:
                    _left_behind(relative, exc)
        try:
            self._files.remove_renditions(asset.content_hash)
        except OSError as exc:
            _left_behind(f"renditions of {asset.content_hash}", exc)


def _left_behind(path: str, exc: OSError) -> None:
    log.warning(
        "could not delete a purged photo's file",
        extra={"path": path, "reason": exc.strerror or str(exc)},
    )
