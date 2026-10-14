"""Ports for background enrichment: offline reverse geocoding, perceptual hashing, and the
exposure settings of photos imported before they were kept."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.exposure import Exposure
from photo_assistant.domain.grouping import Shot
from photo_assistant.domain.places import Place


class Geocoder(Protocol):
    def places_for(self, points: Sequence[tuple[float, float]]) -> list[Place | None]:
        """One result per (lat, lon), same order; None when nowhere near a known place.
        Never calls the network."""
        ...


class PerceptualHasher(Protocol):
    def phash(self, image: Path) -> str:
        """64-bit perceptual hash as 16 hex characters."""
        ...


class EnrichmentStore(Protocol):
    def assets_to_geocode(self, after_id: int, limit: int) -> list[tuple[int, float, float]]: ...
    def set_places(self, places: Sequence[tuple[int, Place]]) -> None: ...
    def assets_without_phash(self, after_id: int, limit: int) -> list[tuple[int, str]]:
        """(asset id, thumbnail path relative to the data root)."""
        ...

    def set_phash(self, asset_id: int, phash: str) -> None: ...
    def shots(self) -> list[Shot]:
        """Every photo in the library (not trashed, not held for review), for grouping."""
        ...

    def shot_times(self) -> list[tuple[int, datetime]]:
        """(asset id, taken_at) of every photo not trashed: finds the runs to regroup."""
        ...

    def shots_in(self, runs: Sequence[tuple[datetime, datetime]]) -> list[Shot]:
        """The photos (not trashed) taken within any of these inclusive time ranges."""
        ...

    def set_groups(self, groups: dict[int, int | None]) -> int:
        """Store group ids; returns how many changed."""
        ...


class ExposureStore(Protocol):
    def assets_without_exposure(self, after_id: int, limit: int) -> list[tuple[int, str]]:
        """(asset id, library path relative to the data root) of photos with none of the four
        exposure values, trashed ones included (they may be restored), by id."""
        ...

    def set_exposures(self, exposures: Sequence[tuple[int, Exposure]]) -> None: ...
    def enqueue(self, kind: str, payload: dict[str, object]) -> int: ...
