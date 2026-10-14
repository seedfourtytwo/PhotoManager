"""The photos taken in the same minute as others, which number their names (display_name.py)."""

import sqlite3
from datetime import datetime

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Level, Role, SourceAccess, Viewer
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.display_name import Dated
from tests.factories import NOW, new_asset

MINUTE = datetime(2015, 6, 12, 14, 32)


def _ids(mates: list[Dated]) -> set[int]:
    return {m.id for m in mates}


def test_mates_share_the_wall_clock_minute_and_are_visible_and_in_the_library(
    repo: SqliteRepository,
) -> None:
    admin = Viewer.of(repo.add_user("admin", "A", "h", Role.ADMIN))
    lea = repo.add_user("lea", "Lea", "h", Role.MEMBER)
    tom = Viewer.of(repo.add_user("tom", "Tom", "h", Role.MEMBER))
    shared = repo.add_source("Family", "/family", access=SourceAccess(Level.DOWNLOAD))
    private = repo.add_source("Lea's", "/lea", lea.id, access=SourceAccess(None))

    def photo(n: int, taken: datetime, source: int, **extra: object) -> int:
        asset_id = repo.add_asset(new_asset(n, taken, **extra), NOW)
        repo.add_asset_source(asset_id, source, f"{n}.jpg")
        return asset_id

    asked = photo(1, MINUTE.replace(second=30), shared.id)
    first = photo(2, MINUTE, shared.id)
    last = photo(3, MINUTE.replace(second=59), shared.id, date_source=DateSource.FILE_MTIME)
    photo(4, MINUTE.replace(minute=31, second=59), shared.id)
    photo(5, MINUTE.replace(minute=33), shared.id)
    hidden_from_tom = photo(6, MINUTE.replace(second=10), private.id)
    trashed = photo(7, MINUTE.replace(second=20), shared.id)
    repo.trash_assets([trashed], admin.user_id, NOW)

    assert _ids(repo.minute_mates(tom, [asked])) == {asked, first, last}
    assert _ids(repo.minute_mates(admin, [asked])) == {asked, first, last, hidden_from_tom}
    found = {m.id: m for m in repo.minute_mates(tom, [asked])}
    assert found[last] == Dated(last, MINUTE.replace(second=59), DateSource.FILE_MTIME)
    assert _ids(repo.minute_mates(tom, [trashed])) == {asked, first, last}, "a trashed photo"
    assert repo.minute_mates(tom, []) == []


def test_mates_of_many_photos_come_from_one_query(
    conn: sqlite3.Connection, repo: SqliteRepository
) -> None:
    admin = Viewer.of(repo.add_user("admin", "A", "h", Role.ADMIN))
    ids = [repo.add_asset(new_asset(n, MINUTE.replace(day=n)), NOW) for n in range(1, 4)]
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        assert _ids(repo.minute_mates(admin, [*ids, *range(1000, 41_000)])) == set(ids)
    finally:
        conn.set_trace_callback(None)
    assert len(statements) == 1, statements
