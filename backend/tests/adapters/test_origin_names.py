"""The original file name offered for a download comes only from a source the viewer may see."""

import sqlite3

import pytest

from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.domain.access import AlbumRole, Level, Role, SourceAccess, Viewer
from tests.factories import NOW, new_asset


@pytest.fixture
def db() -> Database:
    return Database.open(":memory:")


@pytest.fixture
def conn(db: Database) -> sqlite3.Connection:
    return db.writer


@pytest.fixture
def repo(db: Database) -> SqliteRepository:
    return SqliteRepository(db)


class Library:
    """Lea's private folder and a shared one; Tom reaches Lea's photos through an album."""

    def __init__(self, repo: SqliteRepository) -> None:
        self.admin = Viewer.of(repo.add_user("admin", "A", "h", Role.ADMIN))
        lea = repo.add_user("lea", "Lea", "h", Role.MEMBER)
        self.lea = Viewer.of(lea)
        self.tom = Viewer.of(repo.add_user("tom", "Tom", "h", Role.MEMBER))
        private = repo.add_source("Lea's papers", "/lea", lea.id, access=SourceAccess(None))
        shared = repo.add_source("Family", "/family", access=SourceAccess(Level.DOWNLOAD))
        self.only_private, self.both, self.only_shared = (
            repo.add_asset(new_asset(i), NOW) for i in (1, 2, 3)
        )
        repo.add_asset_source(self.only_private, private.id, "2021/Divorce papers.jpg")
        repo.add_asset_source(self.both, private.id, "2021/Clinic letter.jpg")
        repo.add_asset_source(self.both, shared.id, "trip/IMG_0002.JPG")
        repo.add_asset_source(self.only_shared, shared.id, "trip\\IMG_0003.JPG")
        album = repo.create_album(lea.id, "For Tom", "", NOW)
        repo.add_album_items(album, [self.only_private, self.both], None, NOW)
        repo.set_album_members(album, [(self.tom.user_id, AlbumRole.VIEWER)], NOW)
        self.ids = [self.only_private, self.both, self.only_shared]


@pytest.fixture
def lib(repo: SqliteRepository) -> Library:
    return Library(repo)


def test_a_name_from_a_hidden_source_is_not_given_to_someone_who_sees_the_photo_in_an_album(
    repo: SqliteRepository, lib: Library
) -> None:
    assert repo.get_view(lib.tom, lib.only_private) is not None, "the album shows it to Tom"
    assert repo.first_origin_name(lib.tom, lib.only_private) is None
    assert repo.first_origin_name(lib.lea, lib.only_private) == "Divorce papers.jpg"
    assert repo.first_origin_name(lib.admin, lib.only_private) == "Divorce papers.jpg"


def test_the_name_comes_from_the_first_source_the_viewer_may_see(
    repo: SqliteRepository, lib: Library
) -> None:
    assert repo.first_origin_name(lib.lea, lib.both) == "Clinic letter.jpg", "its first source"
    assert repo.first_origin_name(lib.tom, lib.both) == "IMG_0002.JPG"
    assert repo.first_origin_name(lib.tom, lib.only_shared) == "IMG_0003.JPG", "bare name"
    assert repo.first_origin_name(lib.tom, 9999) is None


def test_names_of_many_photos_come_from_one_query(
    conn: sqlite3.Connection, repo: SqliteRepository, lib: Library
) -> None:
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        names = repo.first_origin_names(lib.tom, [*lib.ids, 9999])
    finally:
        conn.set_trace_callback(None)
    assert names == {lib.both: "IMG_0002.JPG", lib.only_shared: "IMG_0003.JPG"}
    assert len(statements) == 1, statements
    assert repo.first_origin_names(lib.tom, []) == {}


def test_names_of_a_whole_library_fit_in_one_query(repo: SqliteRepository, lib: Library) -> None:
    """More ids than SQLite allows as separate parameters."""
    names = repo.first_origin_names(lib.lea, [*lib.ids, *range(1000, 41_000)])
    assert set(names) == set(lib.ids)
