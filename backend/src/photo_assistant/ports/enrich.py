"""Ports for background enrichment: offline reverse geocoding, perceptual hashing."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

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
        """Every photo in the library (not trashed), for grouping."""
        ...

    def set_groups(self, groups: dict[int, int | None]) -> int:
        """Store group ids; returns how many changed."""
        ...
