"""Per-user filters (favourites, hidden) start from the user's own short list of photos (C25)
instead of walking the whole timeline."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_library import ORDER, filter_sql, from_sql, visibility
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.library_filter import AssetFilter
from tests.factories import NOW, new_asset


@pytest.fixture
def conn() -> sqlite3.Connection:
    return open_database(":memory:")


@pytest.fixture
def repo(conn: sqlite3.Connection) -> SqliteRepository:
    return SqliteRepository(conn)


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
