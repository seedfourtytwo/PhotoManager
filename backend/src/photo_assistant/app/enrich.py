"""Background jobs that add knowledge to photos after import (FEATURES 2.4, 2.5).

Both are safe to run any number of times: they only look at photos still missing the data.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.grouping import group_shots, runs_with
from photo_assistant.ports.enrich import EnrichmentStore, Geocoder, PerceptualHasher

log = logging.getLogger(__name__)

GEOCODE_JOB = "geocode"
GROUP_JOB = "group"
FULL_REGROUP: dict[str, object] = {"full": True}  # payload: regroup the whole library


class LookalikeCheck(Protocol):
    def hold_lookalikes(self, new: set[int]) -> int:
        """Hold the new photos that look like one already in the library (issue 8)."""
        ...


class GeocodeAssets:
    """Photos with GPS get a place (country, region, city) from an offline geocoder."""

    def __init__(self, repo: EnrichmentStore, geocoder: Geocoder, batch: int = 500) -> None:
        self._repo = repo
        self._geocoder = geocoder
        self._batch = batch

    def __call__(self, payload: dict[str, object]) -> int:
        done, after = 0, 0
        while todo := self._repo.assets_to_geocode(after, self._batch):
            places = self._geocoder.places_for([(lat, lon) for _, lat, lon in todo])
            found = [(i, p) for (i, _, _), p in zip(todo, places, strict=True) if p is not None]
            self._repo.set_places(found)
            done += len(found)
            after = todo[-1][0]
        return done


class GroupSimilar:
    """Perceptual hash of each thumbnail, then bursts / near-duplicates share a group id."""

    def __init__(
        self,
        repo: EnrichmentStore,
        hasher: PerceptualHasher,
        absolute: Callable[[str], Path],
        batch: int = 500,
        review: LookalikeCheck | None = None,
    ) -> None:
        self._repo = repo
        self._hasher = hasher
        self._absolute = absolute
        self._batch = batch
        self._review = review

    def __call__(self, payload: dict[str, object]) -> int:
        """``{}``: hash the new photos and regroup only the stretches of time they landed in
        (C29). ``{"full": true}``: regroup the whole library."""
        new = self._hash_missing()
        if new and self._review is not None:
            # before grouping: a photo held for review is in no group
            self._review.hold_lookalikes(new)
        if payload.get("full"):
            return self._repo.set_groups(group_shots(self._repo.shots()))
        if not new:
            return 0
        runs = runs_with(self._repo.shot_times(), new)
        return self._repo.set_groups(group_shots(self._repo.shots_in(runs)))

    def _hash_missing(self) -> set[int]:
        """Hash every photo that has a thumbnail but no hash yet; returns their ids."""
        seen: set[int] = set()
        after = 0
        while todo := self._repo.assets_without_phash(after, self._batch):
            for asset_id, thumb in todo:
                seen.add(asset_id)
                try:
                    self._repo.set_phash(asset_id, self._hasher.phash(self._absolute(thumb)))
                except OSError:
                    log.warning("cannot hash thumbnail", extra={"asset_id": asset_id})
            after = todo[-1][0]
        return seen
