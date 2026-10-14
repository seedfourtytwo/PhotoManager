"""Per-user filters (favourites, pinned, hidden) start from the user's own short list of photos
(C25) instead of walking the whole timeline; the person filter goes through the faces."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_library import ORDER, filter_sql, from_sql, visibility
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Role, SourceAccess, Viewer
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.library_filter import AssetFilter
from tests.factories import NOW, new_asset


@pytest.fixture
def member(repo: SqliteRepository) -> Viewer:
    repo.add_user("admin", "A", "h", Role.ADMIN)
    return Viewer.of(repo.add_user("lea", "Lea", "h", Role.MEMBER))


@pytest.fixture
def ids(repo: SqliteRepository, member: Viewer) -> list[int]:
    """Eight photos in a folder everyone sees, oldest first."""
    source = repo.add_source("Family", "/family")
    found = []
    for n in range(1, 9):
        asset_id = repo.add_asset(new_asset(n, datetime(2020, 1, 1) + timedelta(days=n)), NOW)
        repo.add_asset_source(asset_id, source.id, f"{n}.jpg")
        found.append(asset_id)
    return found


def _plan(conn: sqlite3.Connection, viewer: Viewer, f: AssetFilter) -> str:
    visible, _, params = visibility(viewer)
    where, fparams = filter_sql(f)
    sql = f"EXPLAIN QUERY PLAN SELECT a.id {from_sql(f)} {where} AND {visible} {ORDER}"
    return "\n".join(str(row["detail"]) for row in conn.execute(sql, params | fparams))


@pytest.mark.parametrize(
    "f",
    [
        AssetFilter(hidden=True),
        AssetFilter(favourite=True),
        AssetFilter(favourite=True, hidden=True),
        AssetFilter(pinned=True),
        AssetFilter(pinned=True, favourite=True),
    ],
)
def test_my_hidden_and_favourite_photos_are_found_without_walking_the_timeline(
    conn: sqlite3.Connection, member: Viewer, ids: list[int], f: AssetFilter
) -> None:
    plan = _plan(conn, member, f)
    assert "SCAN a" not in plan, plan
    assert "SCAN fav" in plan or "SEARCH fav" in plan, plan


def test_the_hidden_filter_lists_exactly_my_hidden_photos_newest_first(
    repo: SqliteRepository, member: Viewer, ids: list[int]
) -> None:
    other = Viewer.of(repo.add_user("tom", "Tom", "h", Role.MEMBER))
    repo.set_user_state(member.user_id, [ids[1], ids[5]], hidden=True)
    repo.set_user_state(member.user_id, [ids[5], ids[6]], favourite=True)
    repo.set_user_state(other.user_id, [ids[2]], hidden=True)
    assert repo.visible_asset_ids(member, AssetFilter(hidden=True)) == [ids[5], ids[1]]
    assert repo.visible_asset_ids(member, AssetFilter(hidden=True, favourite=True)) == [ids[5]]
    assert repo.visible_asset_ids(member, AssetFilter(favourite=True)) == [ids[6]]
    assert repo.visible_asset_ids(member, AssetFilter(hidden=True, favourite=False)) == [ids[1]]
    page = repo.list_views(member, AssetFilter(hidden=True), limit=1)
    assert [v.id for v in page.items] == [ids[5]] and page.items[0].hidden
    assert page.next_cursor is not None
    assert repo.facets(member, AssetFilter(hidden=True)).total == 2
    assert len(repo.visible_asset_ids(member)) == 6, "hidden photos stay out by default"


# --- pinned (issue 54): per account, like favourites ------------------------------------------


def _pinned_at(conn: sqlite3.Connection, user_id: int, asset_id: int) -> str | None:
    row = conn.execute(
        "SELECT pinned_at FROM user_asset WHERE user_id = ? AND asset_id = ?", (user_id, asset_id)
    ).fetchone()
    return None if row is None else row[0]


def test_pinned_photos_are_mine_alone_and_listed_newest_first(
    repo: SqliteRepository, member: Viewer, ids: list[int]
) -> None:
    other = Viewer.of(repo.add_user("tom", "Tom", "h", Role.MEMBER))
    assert repo.set_pinned(member.user_id, [ids[1], ids[4]], True, NOW) == 2
    repo.set_pinned(other.user_id, [ids[2]], True, NOW)
    assert repo.visible_asset_ids(member, AssetFilter(pinned=True)) == [ids[4], ids[1]]
    assert len(repo.visible_asset_ids(member, AssetFilter(pinned=False))) == 6
    assert repo.visible_asset_ids(other, AssetFilter(pinned=True)) == [ids[2]]
    mine, theirs = repo.get_view(member, ids[4]), repo.get_view(other, ids[4])
    assert mine is not None and mine.pinned and not mine.favourite
    assert theirs is not None and not theirs.pinned
    assert repo.facets(member, AssetFilter(pinned=True)).total == 2
    assert len(repo.visible_asset_ids(member)) == 8, "pinning takes nothing off the timeline"


def test_pinning_again_keeps_the_first_time_and_unpinning_clears_it(
    repo: SqliteRepository, conn: sqlite3.Connection, member: Viewer, ids: list[int]
) -> None:
    repo.set_pinned(member.user_id, [ids[0]], True, NOW)
    repo.set_pinned(member.user_id, [ids[0]], True, NOW + timedelta(days=1))
    assert _pinned_at(conn, member.user_id, ids[0]) == utc_text(NOW)
    repo.set_user_state(member.user_id, [ids[0]], favourite=True)
    repo.set_pinned(member.user_id, [ids[0]], False, NOW)
    assert _pinned_at(conn, member.user_id, ids[0]) is None
    view = repo.get_view(member, ids[0])
    assert view is not None and view.favourite and not view.pinned, "favourite stays"
    repo.set_pinned(member.user_id, [ids[3]], False, NOW)
    assert _pinned_at(conn, member.user_id, ids[3]) is None, "unpinning an unpinned photo: no-op"


# --- people (person_id): photos with ANY of the given people ----------------------------------


@pytest.fixture
def people(db: Database, repo: SqliteRepository, ids: list[int]) -> dict[str, int]:
    """Lea is on photos 1 and 3, Tom on 3 and 5 (two faces on photo 3), nobody on the others.
    A ninth photo with Lea sits in a folder only admins see."""
    store = SqliteMlStore(db)
    vector = (1.0, 0.0, 0.0, 0.0)

    def faces(asset_id: int, n: int = 1) -> list[int]:
        boxes = [BoundingBox(0.5 * i, 0, 0.4, 0.4) for i in range(n)]
        return store.replace_faces(asset_id, "f", [Face(b, 0.9, (), vector) for b in boxes])

    secret = repo.add_source("Admins only", "/secret", access=SourceAccess(None))
    hidden_photo = repo.add_asset(new_asset(9, datetime(2020, 1, 20)), NOW)
    repo.add_asset_source(hidden_photo, secret.id, "9.jpg")
    (on_1,), (lea_on_3, tom_on_3), (on_5,) = faces(ids[0]), faces(ids[2], 2), faces(ids[4])
    (on_secret,) = faces(hidden_photo)
    lea = store.create_person(on_1)
    for face_id in (lea_on_3, on_secret):
        store.assign_face(face_id, lea)
    tom = store.create_person(tom_on_3)
    store.assign_face(on_5, tom)
    return {"lea": lea, "tom": tom, "secret": hidden_photo}


def test_the_person_filter_lists_photos_with_any_of_the_people_once(
    repo: SqliteRepository, member: Viewer, ids: list[int], people: dict[str, int]
) -> None:
    lea, tom = people["lea"], people["tom"]
    assert repo.visible_asset_ids(member, AssetFilter(person_ids=(lea,))) == [ids[2], ids[0]]
    both = AssetFilter(person_ids=(lea, tom))
    assert repo.visible_asset_ids(member, both) == [ids[4], ids[2], ids[0]]
    assert [v.id for v in repo.list_views(member, both, limit=10).items] == [ids[4], ids[2], ids[0]]
    assert repo.visible_asset_ids(member, AssetFilter(person_ids=(999,))) == []
    assert repo.facets(member, both).total == 3
    assert [c.key for c in repo.calendar(member, AssetFilter(person_ids=(tom,)))] == [
        "2020-01-04",
        "2020-01-06",
    ]


def test_the_person_filter_never_widens_what_a_viewer_sees(
    repo: SqliteRepository, member: Viewer, ids: list[int], people: dict[str, int]
) -> None:
    admin = Viewer(1, Role.ADMIN)
    lea = AssetFilter(person_ids=(people["lea"],))
    assert people["secret"] not in repo.visible_asset_ids(member, lea)
    assert repo.visible_asset_ids(admin, lea) == [people["secret"], ids[2], ids[0]]


def test_the_person_filter_combines_with_the_others(
    repo: SqliteRepository, member: Viewer, ids: list[int], people: dict[str, int]
) -> None:
    repo.set_user_state(member.user_id, [ids[2]], favourite=True)
    repo.set_user_state(member.user_id, [ids[0]], hidden=True)
    lea = (people["lea"],)
    assert repo.visible_asset_ids(member, AssetFilter(person_ids=lea, favourite=True)) == [ids[2]]
    assert repo.visible_asset_ids(member, AssetFilter(person_ids=lea)) == [ids[2]], "hidden: out"
    to_day = AssetFilter(person_ids=(people["tom"],), to_day=datetime(2020, 1, 4).date())
    assert repo.visible_asset_ids(member, to_day) == [ids[2]]
