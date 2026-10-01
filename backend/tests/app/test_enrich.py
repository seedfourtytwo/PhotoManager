"""Background enrichment with fakes: places from GPS, perceptual hashes, groups."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.enrich import GeocodeAssets, GroupSimilar
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.places import Place
from photo_assistant.ports import RenderedImage
from tests.factories import NOW, new_asset

ADMIN = Viewer(1, Role.ADMIN)


class FakeGeocoder:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def places_for(self, points: Sequence[tuple[float, float]]) -> list[Place | None]:
        self.calls.append(len(points))
        return [Place("France", "Brittany", "Quimper") if lat > 0 else None for lat, _ in points]


class FakeHasher:
    def phash(self, image: Path) -> str:
        return "0000000000000000" if "similar" in image.name else "ffffffffffffffff"


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


def test_geocoding_fills_places_in_batches(repo: SqliteRepository) -> None:
    north = [repo.add_asset(new_asset(i, latitude=48.0, longitude=-4.1), NOW) for i in range(5)]
    south = repo.add_asset(new_asset(10, latitude=-1.0, longitude=0.0), NOW)
    no_gps = repo.add_asset(new_asset(11), NOW)
    geocoder = FakeGeocoder()
    assert GeocodeAssets(repo, geocoder, batch=2)({}) == 5
    assert geocoder.calls == [2, 2, 2]
    views = repo.list_all_views(ADMIN, AssetFilter())
    places = {v.id: v.place for v in views}
    assert all(places[i] == Place("France", "Brittany", "Quimper") for i in north)
    assert places[south] is None and places[no_gps] is None
    assert GeocodeAssets(repo, geocoder)({}) == 0, "only the one far from anywhere is retried"


def test_grouping_hashes_thumbnails_and_groups_near_duplicates(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    times = [datetime(2024, 1, 1, 10, 0, s) for s in (0, 30, 59)]
    ids = []
    for n, (taken, name) in enumerate(zip(times, ["similar-a", "similar-b", "other"], strict=True)):
        asset_id = repo.add_asset(new_asset(n, taken_at=taken, camera_model=f"cam{n}"), NOW)
        repo.set_thumbnail(asset_id, RenderedImage(f"thumbs/{name}.webp", 10, 10))
        ids.append(asset_id)
    lonely = repo.add_asset(new_asset(9), NOW)  # no thumbnail yet: no hash, no group
    grouper = GroupSimilar(repo, FakeHasher(), lambda rel: tmp_path / rel)
    assert grouper({}) == 2
    groups = {v.id: v.group_id for v in repo.list_all_views(ADMIN, AssetFilter())}
    assert groups == {ids[0]: ids[0], ids[1]: ids[0], ids[2]: None, lonely: None}
    assert grouper({}) == 0, "idempotent"
