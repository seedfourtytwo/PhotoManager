"""The photos per (country, city) one viewer may see, under the rules the facets use."""

from datetime import datetime

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.places import Place, PlaceGroup
from photo_assistant.ports import RenderedImage
from tests.factories import NOW, new_asset


@pytest.fixture
def member(repo: SqliteRepository) -> Viewer:
    repo.add_user("admin", "A", "h", Role.ADMIN)
    return Viewer.of(repo.add_user("lea", "Lea", "h", Role.MEMBER))


def _photo(
    repo: SqliteRepository,
    source_id: int,
    n: int,
    place: Place | None,
    gps: tuple[float, float] | None = None,
    *,
    day: int = 1,
    thumb: bool = True,
) -> int:
    lat, lon = gps or (None, None)
    asset = new_asset(n, datetime(2020, 1, day, 12, 0), latitude=lat, longitude=lon)
    asset_id = repo.add_asset(asset, NOW)
    repo.add_asset_source(asset_id, source_id, f"{n}.jpg")
    if place:
        repo.set_places([(asset_id, place)])
    if thumb:
        repo.set_thumbnail(asset_id, RenderedImage(f"derived/thumb/{n}.webp", 64, 48))
    return asset_id


def test_groups_count_centre_and_cover_what_the_viewer_may_see(
    repo: SqliteRepository, member: Viewer
) -> None:
    family = repo.add_source("Family", "/family").id
    closed = repo.add_source("Admin only", "/admin").id
    repo.set_access(closed, None, [])
    paris = Place("France", "IDF", "Paris")
    a = _photo(repo, family, 1, paris, (48.0, 2.0), day=1)
    b = _photo(repo, family, 2, paris, (49.0, 3.0), day=3)
    newest_no_thumb = _photo(repo, family, 3, paris, day=5, thumb=False)
    hidden = _photo(repo, family, 4, paris, (10.0, 10.0), day=9)
    repo.set_user_state(member.user_id, [hidden], hidden=True)
    _photo(repo, closed, 5, paris, (0.0, 0.0), day=9)
    country_only = _photo(repo, family, 6, Place("France"), day=2)
    _photo(repo, family, 7, None, (1.0, 1.0))

    groups = sorted(repo.place_groups(member), key=lambda g: g.city)
    assert groups == [
        PlaceGroup("France", "", 1, 0, None, None, country_only, "2020-01-02T12:00:00"),
        PlaceGroup("France", "Paris", 3, 2, 48.5, 2.5, b, "2020-01-03T12:00:00"),
    ]
    assert a and newest_no_thumb, "counted, but neither is the cover"


def test_no_places_gives_no_groups(repo: SqliteRepository, member: Viewer) -> None:
    family = repo.add_source("Family", "/family").id
    _photo(repo, family, 1, None)
    assert repo.place_groups(member) == []
