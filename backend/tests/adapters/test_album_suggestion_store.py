"""What suggested albums read and remember (FEATURES 5.6): the photos events are made of, as the
timeline shows them to the viewer, and each account's Keep or Discard."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Role, SourceAccess, Viewer
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.events import EventPhoto
from photo_assistant.domain.places import Place
from tests.factories import NOW, new_asset

JULY = datetime(2025, 7, 12, 10)


@pytest.fixture
def member(repo: SqliteRepository) -> Viewer:
    repo.add_user("admin", "A", "h", Role.ADMIN)
    return Viewer.of(repo.add_user("lea", "Lea", "h", Role.MEMBER))


def _photo(repo: SqliteRepository, n: int, source: int, **overrides: object) -> int:
    asset_id = repo.add_asset(new_asset(n, JULY + timedelta(hours=n), **overrides), NOW)
    repo.add_asset_source(asset_id, source, f"{n}.jpg")
    return asset_id


def _face(repo: SqliteRepository, asset_id: int, person_id: int | None) -> None:
    repo._write(
        """INSERT INTO face (asset_id, model, box_x, box_y, box_w, box_h, score,
               landmarks_json, dim, embedding, person_id)
           VALUES (?, 'm', 0, 0, 1, 1, 1, '[]', 1, zeroblob(4), ?)""",
        (asset_id, person_id),
    )


def test_event_photos_are_what_the_viewer_sees_with_gps_people_and_place(
    repo: SqliteRepository, member: Viewer
) -> None:
    family = repo.add_source("Family", "/family").id
    secret = repo.add_source("Admins only", "/secret", access=SourceAccess(None)).id
    malo = _photo(repo, 1, family, latitude=48.65, longitude=-2.03)
    bare = _photo(repo, 2, family)
    _photo(repo, 3, family, date_source=DateSource.FILE_MTIME)
    hidden = _photo(repo, 4, family)
    _photo(repo, 5, secret)
    repo.set_places([(malo, Place("France", "Brittany", "Saint-Malo"))])
    repo.set_user_state(member.user_id, [hidden], hidden=True)
    sam = repo._write("INSERT INTO person (name) VALUES ('Sam')")
    leo = repo._write("INSERT INTO person (name) VALUES (NULL)")
    _face(repo, malo, sam)
    _face(repo, malo, leo)
    _face(repo, malo, None)  # a face nobody is named for

    found = {p.asset_id: p for p in repo.event_photos(member)}

    assert set(found) == {malo, bare}, "a date guessed from the file is no date"
    assert found[malo] == EventPhoto(
        malo,
        JULY + timedelta(hours=1),
        (48.65, -2.03),
        frozenset({sam, leo}),
        Place("France", "Brittany", "Saint-Malo"),
    )
    assert found[bare] == EventPhoto(bare, JULY + timedelta(hours=2), None)


def test_photos_in_albums_are_those_in_albums_the_viewer_sees(
    repo: SqliteRepository, member: Viewer
) -> None:
    family = repo.add_source("Family", "/family").id
    mine, theirs = (_photo(repo, n, family) for n in (1, 2))
    own = repo.create_album(member.user_id, "Mine", "", NOW)
    repo.add_album_items(own, [mine], None, NOW)
    other = repo.create_album(1, "Admin's", "", NOW)
    repo.add_album_items(other, [theirs], None, NOW)

    assert repo.photos_in_albums(member) == {mine}


def test_keeping_makes_the_album_with_its_photos_once(
    repo: SqliteRepository, member: Viewer
) -> None:
    family = repo.add_source("Family", "/family").id
    photos = [_photo(repo, n, family) for n in (1, 2, 3)]

    album_id = repo.keep_suggestion(member.user_id, "1", "Brittany · July 2025", photos, NOW)

    assert album_id is not None
    info = repo.album_info(member, album_id)
    assert info is not None
    assert (info.title, info.owner_id, info.count) == ("Brittany · July 2025", member.user_id, 3)
    assert repo.album_asset_ids(album_id) == photos
    assert repo.suggestion_answers(member.user_id) == {"1"}
    assert repo.keep_suggestion(member.user_id, "1", "Again", photos, NOW) is None
    assert len(repo.list_albums(member)) == 1


def test_discarding_is_remembered_per_account(repo: SqliteRepository, member: Viewer) -> None:
    assert repo.discard_suggestion(member.user_id, "7", NOW) is True
    assert repo.discard_suggestion(member.user_id, "7", NOW) is False
    assert repo.suggestion_answers(member.user_id) == {"7"}
    assert repo.suggestion_answers(1) == set()
    assert repo.keep_suggestion(member.user_id, "7", "Late", [], NOW) is None


def test_a_kept_album_deleted_later_leaves_the_answer(repo: SqliteRepository, member: Viewer) -> None:
    family = repo.add_source("Family", "/family").id
    album_id = repo.keep_suggestion(member.user_id, "1", "T", [_photo(repo, 1, family)], NOW)
    assert album_id is not None
    repo.delete_album(album_id)
    assert repo.suggestion_answers(member.user_id) == {"1"}
