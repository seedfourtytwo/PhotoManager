"""Trash (FEATURES 11.3): soft delete, restore, purge of the library copy, 30-day expiry."""

import stat
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.trash import TRASH_DAYS, Trash
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.ports import RenderedImage
from tests.factories import NOW, new_asset

ADMIN = Viewer(1, Role.ADMIN)


class MovableClock:
    def __init__(self) -> None:
        self.at = NOW

    def now(self) -> datetime:
        return self.at


@pytest.fixture
def world(tmp_path: Path) -> tuple[SqliteRepository, DiskLibraryStore, MovableClock, Trash]:
    repo = SqliteRepository(open_database(":memory:"))
    repo.add_user("c", "C", "hash", Role.ADMIN)
    store = DiskLibraryStore(tmp_path / "data")
    clock = MovableClock()
    return repo, store, clock, Trash(repo, store, clock)


def library_photo(repo: SqliteRepository, store: DiskLibraryStore, n: int) -> int:
    asset = new_asset(n)
    asset_id = repo.add_asset(asset, NOW)
    for rel in (asset.library_path, f"derived/thumb/{n}.webp", f"derived/preview/{n}.webp"):
        path = store.absolute(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    store.absolute(asset.library_path).chmod(0o444)  # originals are read-only
    edited = store.absolute(f"derived/edited/{asset.content_hash[:2]}/{asset.content_hash}-k.webp")
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_bytes(b"e")
    repo.set_thumbnail(asset_id, RenderedImage(f"derived/thumb/{n}.webp", 1, 1))
    repo.set_preview(asset_id, RenderedImage(f"derived/preview/{n}.webp", 1, 1))
    return asset_id


def visible(repo: SqliteRepository) -> set[int]:
    return {v.id for v in repo.list_all_views(ADMIN, AssetFilter())}


def test_trash_hides_and_restore_brings_back(world) -> None:  # type: ignore[no-untyped-def]
    repo, store, _, trash = world
    a, b = library_photo(repo, store, 1), library_photo(repo, store, 2)
    assert trash.trash([a], user_id=1) == 1
    assert trash.trash([a], user_id=1) == 0, "already in the trash"
    assert visible(repo) == {b}
    assert [v.id for v in repo.trashed_views(ADMIN)] == [a]
    assert trash.restore([a]) == 1
    assert visible(repo) == {a, b}


def test_purge_removes_library_copy_and_derivatives_and_remembers_the_hash(world) -> None:  # type: ignore[no-untyped-def]
    repo, store, _, trash = world
    a = library_photo(repo, store, 1)
    asset = repo.get_asset(a)
    assert asset is not None
    original = store.absolute(asset.library_path)
    assert not original.stat().st_mode & stat.S_IWUSR
    assert trash.empty([a]) == 0, "only photos in the trash are purged"
    trash.trash([a], user_id=1)
    assert trash.empty(None) == 1
    assert not original.exists()
    assert not store.absolute("derived/thumb/1.webp").exists()
    assert not store.absolute("derived/preview/1.webp").exists()
    assert not list(store.absolute("derived/edited").rglob("*.webp"))
    assert repo.get_asset(a) is None
    assert repo.is_purged_hash(asset.content_hash)
    assert repo.trashed_views(ADMIN) == []


def test_expired_items_are_purged_after_thirty_days(world) -> None:  # type: ignore[no-untyped-def]
    repo, store, clock, trash = world
    old, recent = library_photo(repo, store, 1), library_photo(repo, store, 2)
    trash.trash([old], user_id=1)
    clock.at += timedelta(days=20)
    trash.trash([recent], user_id=1)
    clock.at += timedelta(days=TRASH_DAYS - 20, seconds=1)
    assert trash.purge_expired({}) == 1
    assert repo.get_asset(old) is None and repo.get_asset(recent) is not None


def test_store_refuses_to_remove_anything_outside_the_library(world) -> None:  # type: ignore[no-untyped-def]
    _, store, _, _ = world
    with pytest.raises(ValueError, match="library"):
        store.remove("tmp/whatever")
    store.remove("originals/2020/01/missing.jpg")  # missing is fine
