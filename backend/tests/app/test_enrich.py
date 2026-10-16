"""Background enrichment with fakes: places from GPS, perceptual hashes, groups."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.enrich import GeocodeAssets, GroupSimilar, PaintColours
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


def test_new_photos_regroup_only_their_own_stretch_of_time(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    """C29: a new photo next to an old one joins its group; photos hours away aren't read."""
    early = [datetime(2024, 1, 1, 10, 0, s) for s in (0, 30)]
    far = datetime(2024, 1, 1, 18, 0, 0)
    grouper = GroupSimilar(repo, FakeHasher(), lambda rel: tmp_path / rel)
    a = repo.add_asset(new_asset(1, taken_at=early[0], camera_model="x"), NOW)
    repo.set_thumbnail(a, RenderedImage("thumbs/similar-a.webp", 10, 10))
    lone = repo.add_asset(new_asset(2, taken_at=far, camera_model="y"), NOW)
    repo.set_thumbnail(lone, RenderedImage("thumbs/other.webp", 10, 10))
    grouper({})
    b = repo.add_asset(new_asset(3, taken_at=early[1], camera_model="z"), NOW)
    repo.set_thumbnail(b, RenderedImage("thumbs/similar-b.webp", 10, 10))

    read: list[int] = []
    real = repo.shots_in

    def spy(runs):  # type: ignore[no-untyped-def]
        found = real(runs)
        read.extend(s.asset_id for s in found)
        return found

    repo.shots_in = spy  # type: ignore[method-assign]
    assert grouper({}) == 2, "a and b now form a group"
    assert sorted(read) == [a, b], "the photo hours away was not regrouped"
    groups = {v.id: v.group_id for v in repo.list_all_views(ADMIN, AssetFilter())}
    assert groups == {a: a, b: a, lone: None}
    assert grouper({"full": True}) == 0, "a full regroup agrees"


class FakeSampler:
    """Thumbnails named ``red…`` are red; ``broken…`` cannot be read."""

    def __init__(self) -> None:
        self.read: list[str] = []

    def colour_sample(self, image: Path) -> list[tuple[int, int, int]]:
        self.read.append(image.name)
        if image.name.startswith("broken"):
            raise OSError("not a picture")
        return [(200, 30, 30)] * 4 if image.name.startswith("red") else [(20, 40, 210)]


def test_colours_are_painted_for_photos_with_a_thumbnail_in_batches(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    ids = []
    for n, name in enumerate(["red-a", "blue-b", "broken-c", "red-d"]):
        asset_id = repo.add_asset(new_asset(n), NOW)
        repo.set_thumbnail(asset_id, RenderedImage(f"thumbs/{name}.webp", 10, 10))
        ids.append(asset_id)
    no_thumb = repo.add_asset(new_asset(9), NOW)
    sampler = FakeSampler()
    assert PaintColours(repo, sampler, lambda rel: tmp_path / rel, batch=2)({}) == 3
    colours = {v.id: v.asset.colour for v in repo.list_all_views(ADMIN, AssetFilter())}
    assert colours == {
        ids[0]: "#c81e1e",
        ids[1]: "#1428d2",
        ids[2]: None,  # its thumbnail could not be read: tried again next time
        ids[3]: "#c81e1e",
        no_thumb: None,
    }
    sampler.read.clear()
    assert PaintColours(repo, sampler, lambda rel: tmp_path / rel)({}) == 0
    assert sampler.read == ["broken-c.webp"], "only the photo still without one is read again"
