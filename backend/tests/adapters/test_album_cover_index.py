"""Deleting a photo looks for the albums it is the cover of by index (migration 0025), both
in the purge's own UPDATE and in the foreign-key check of ``DELETE FROM asset``."""

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from tests.factories import NOW, new_asset


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


def _plan(repo: SqliteRepository, sql: str) -> list[str]:
    rows = repo._conn.execute(f"EXPLAIN QUERY PLAN {sql}", (1,))
    return [str(row["detail"]) for row in rows]


def test_the_foreign_key_check_of_deleting_a_photo_does_not_scan_the_albums(
    repo: SqliteRepository,
) -> None:
    plan = _plan(repo, "DELETE FROM asset WHERE id = ?")

    albums = [step for step in plan if step.split()[1] == "album"]
    assert albums, plan
    assert all(step.startswith("SEARCH album USING") for step in albums), plan
    assert all("INDEX album_by_cover (cover_asset_id=?)" in step for step in albums), plan
    assert not any(step.startswith("SCAN album") for step in plan), plan


def test_clearing_the_cover_of_a_purged_photo_uses_the_index(repo: SqliteRepository) -> None:
    plan = _plan(repo, "UPDATE album SET cover_asset_id = NULL WHERE cover_asset_id = ?")
    assert plan == ["SEARCH album USING COVERING INDEX album_by_cover (cover_asset_id=?)"], plan


def test_a_purged_cover_photo_still_leaves_its_album_without_a_cover(
    repo: SqliteRepository,
) -> None:
    asset_id = repo.add_asset(new_asset(1), NOW)
    repo._conn.execute(
        "INSERT INTO user (id, username, display_name, password_hash, role, created_at) "
        "VALUES (1, 'ck', 'C', 'x', 'admin', ?)",
        (NOW.isoformat(),),
    )
    repo._conn.execute(
        "INSERT INTO album (owner_id, title, cover_asset_id, created_at, updated_at) "
        "VALUES (1, 'Trip', ?, ?, ?)",
        (asset_id, NOW.isoformat(), NOW.isoformat()),
    )
    repo._conn.execute("UPDATE asset SET trashed_at = ? WHERE id = ?", (NOW.isoformat(), asset_id))
    asset = repo.get_asset(asset_id)
    assert asset is not None

    assert repo.purge_asset(asset, NOW) is True
    assert repo._conn.execute("SELECT cover_asset_id FROM album").fetchone()[0] is None
