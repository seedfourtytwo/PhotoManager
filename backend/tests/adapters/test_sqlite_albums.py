"""Album items on SQLite: order, and the work done per photo while the write lock is held."""

from collections.abc import Iterator

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.domain.access import Role
from tests.factories import NOW, new_asset

ALBUM_SIZE = 40


class CountingList(list[int]):
    """A list that knows how often it was walked from the start."""

    walks = 0

    def __iter__(self) -> Iterator[int]:
        self.walks += 1
        return super().__iter__()


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


@pytest.fixture
def album(repo: SqliteRepository) -> tuple[int, list[int]]:
    owner = repo.add_user("ck", "C", "hash", Role.ADMIN)
    ids = [repo.add_asset(new_asset(i), NOW) for i in range(1, ALBUM_SIZE + 11)]
    album_id = repo.create_album(owner.id, "Trip", "", NOW)
    repo.add_album_items(album_id, ids[:ALBUM_SIZE], None, NOW)
    return album_id, ids


def test_adding_photos_does_not_rebuild_the_album_once_per_photo(
    repo: SqliteRepository, album: tuple[int, list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    album_id, ids = album
    current = CountingList(repo.album_asset_ids(album_id))
    monkeypatch.setattr(repo, "album_asset_ids", lambda _album: current)
    added = repo.add_album_items(album_id, [*ids[ALBUM_SIZE:], ids[0]], ids[1], NOW)
    monkeypatch.undo()
    assert added == 10, "a photo already in the album is skipped"
    assert current.walks < 10, f"the album was walked {current.walks} times for 11 photos"
    assert repo.album_asset_ids(album_id) == [ids[0], *ids[ALBUM_SIZE:], *ids[1:ALBUM_SIZE]]


def test_reordering_does_not_rebuild_the_request_once_per_photo(
    repo: SqliteRepository, album: tuple[int, list[int]]
) -> None:
    album_id, ids = album
    first = CountingList([ids[5], ids[2]])
    repo.reorder_album(album_id, first, NOW)
    assert first.walks < 10, f"the request was walked {first.walks} times for {ALBUM_SIZE} photos"
    rest = [i for i in ids[:ALBUM_SIZE] if i not in (ids[5], ids[2])]
    assert repo.album_asset_ids(album_id) == [ids[5], ids[2], *rest]


def test_reordering_rejects_photos_outside_the_album_and_repeats(
    repo: SqliteRepository, album: tuple[int, list[int]]
) -> None:
    album_id, ids = album
    with pytest.raises(ValueError, match="each once"):
        repo.reorder_album(album_id, [ids[-1]], NOW)
    with pytest.raises(ValueError, match="each once"):
        repo.reorder_album(album_id, [ids[0], ids[0]], NOW)
    assert repo.album_asset_ids(album_id) == ids[:ALBUM_SIZE]
