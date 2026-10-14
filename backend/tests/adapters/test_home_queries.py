"""What Home reads (issue 54): the photos memories are made of, and what arrived lately. Both
follow the timeline's rules: what the viewer may see, not in the trash, not held, not hidden."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Role, SourceAccess, Viewer
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.memories import Moment
from photo_assistant.domain.places import Place
from photo_assistant.ports.library import Count
from tests.factories import NOW, new_asset

JULY = datetime(2024, 7, 3, 10)


@pytest.fixture
def member(repo: SqliteRepository) -> Viewer:
    repo.add_user("admin", "A", "h", Role.ADMIN)
    return Viewer.of(repo.add_user("lea", "Lea", "h", Role.MEMBER))


def _photo(
    repo: SqliteRepository,
    n: int,
    source: int,
    *,
    imported: datetime = NOW,
    taken: datetime | None = None,
) -> int:
    asset_id = repo.add_asset(new_asset(n, taken or JULY + timedelta(hours=n)), imported)
    repo.add_asset_source(asset_id, source, f"{n}.jpg")
    return asset_id


def test_moments_are_what_the_viewer_sees_with_a_real_date_in_time_order(
    repo: SqliteRepository, member: Viewer
) -> None:
    family = repo.add_source("Family", "/family").id
    secret = repo.add_source("Admins only", "/secret", access=SourceAccess(None)).id
    lisbon, porto, mine, hidden, trashed, held, guessed = (
        _photo(repo, n, family) for n in range(1, 8)
    )
    _photo(repo, 8, secret)
    later = _photo(repo, 9, family, taken=JULY + timedelta(days=30))
    repo.set_places(
        [(lisbon, Place("Portugal", "Lisboa", "Lisbon")), (porto, Place("Portugal", "Porto", ""))]
    )
    repo.set_user_state(member.user_id, [mine], favourite=True)
    repo.set_user_state(member.user_id, [hidden], hidden=True)
    repo.trash_assets([trashed], member.user_id, NOW)
    repo.hold_asset(held, "screenshot", None)
    repo._write(
        "UPDATE asset SET date_source = ? WHERE id = ?", (DateSource.FILE_MTIME.value, guessed)
    )

    found = repo.moments(member)

    assert found == [
        Moment(lisbon, JULY + timedelta(hours=1), "Lisbon"),
        Moment(porto, JULY + timedelta(hours=2), "Porto", False),
        Moment(mine, JULY + timedelta(hours=3), None, True),
        Moment(later, JULY + timedelta(days=30), None),
    ]


def test_arrivals_are_the_newest_imports_with_the_folders_they_came_from(
    repo: SqliteRepository, member: Viewer
) -> None:
    phone = repo.add_source("Phone", "/phone").id
    camera = repo.add_source("Camera", "/camera").id
    secret = repo.add_source("Admins only", "/secret", access=SourceAccess(None)).id
    since = NOW - timedelta(days=7)
    old = _photo(repo, 1, phone, imported=since - timedelta(seconds=1))
    edge = _photo(repo, 2, phone, imported=since)
    fresh = [_photo(repo, n, camera, imported=NOW - timedelta(hours=n)) for n in range(3, 6)]
    hidden = _photo(repo, 6, phone, imported=NOW)
    repo.set_user_state(member.user_id, [hidden], hidden=True)
    shared = _photo(repo, 7, secret, imported=NOW - timedelta(minutes=1))
    repo.add_asset_source(shared, phone, "copy-of-7.jpg")  # seen through the phone folder
    _photo(repo, 8, secret, imported=NOW)

    found = repo.arrivals(member, since, limit=3)

    assert found.count == 5 and old not in found.newest
    assert found.newest == [shared, fresh[0], fresh[1]]
    assert found.sources == [Count(str(camera), 3, "Camera"), Count(str(phone), 1, "Phone")]
    assert repo.arrivals(member, since, limit=10).newest[-1] == edge


def test_no_photos_nothing_read(repo: SqliteRepository, member: Viewer) -> None:
    assert repo.moments(member) == []
    empty = repo.arrivals(member, NOW, limit=12)
    assert (empty.count, empty.newest, empty.sources) == (0, [], [])
