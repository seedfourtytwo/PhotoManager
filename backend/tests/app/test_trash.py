"""Trash (FEATURES 11.3): soft delete, restore, purge of the library copy, 30-day expiry."""

import stat
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
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
    repo = SqliteRepository(Database.open(":memory:"))
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
    printed = store.absolute(f"derived/print/{asset.content_hash[:2]}/{asset.content_hash}-k.jpg")
    printed.parent.mkdir(parents=True, exist_ok=True)
    printed.write_bytes(b"p")
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
    assert trash.empty(ADMIN, [a]) == 0, "only photos in the trash are purged"
    trash.trash([a], user_id=1)
    assert trash.empty(ADMIN, None) == 1
    assert not original.exists()
    assert not store.absolute("derived/thumb/1.webp").exists()
    assert not store.absolute("derived/preview/1.webp").exists()
    assert not list(store.absolute("derived/edited").rglob("*.webp"))
    assert not list(store.absolute("derived/print").rglob("*.jpg")), "print renditions go too"
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


# --- QA A2: a restore that lands while the purge runs must win -------------------------------


class RestoreDuringPurge:
    """The repository, except that a restore lands right after the purge picked its photos."""

    def __init__(self, repo: SqliteRepository, restore: list[int]) -> None:
        self._repo = repo
        self._restore = restore

    def __getattr__(self, name: str) -> object:
        return getattr(self._repo, name)

    def purge_candidates(self, ids, trashed_before):  # type: ignore[no-untyped-def]
        found = self._repo.purge_candidates(ids, trashed_before)
        self._repo.restore_assets(self._restore)
        return found


def test_a_photo_restored_while_the_trash_is_emptied_is_kept_with_its_files(world) -> None:  # type: ignore[no-untyped-def]
    repo, store, clock, _ = world
    kept, gone = library_photo(repo, store, 1), library_photo(repo, store, 2)
    Trash(repo, store, clock).trash([kept, gone], user_id=1)
    racing = Trash(RestoreDuringPurge(repo, [kept]), store, clock)  # type: ignore[arg-type]
    assert racing.empty(ADMIN, None) == 1
    asset = repo.get_asset(kept)
    assert asset is not None, "the restored photo must survive"
    assert store.absolute(asset.library_path).is_file()
    assert store.absolute("derived/thumb/1.webp").is_file()
    assert not repo.is_purged_hash(asset.content_hash)
    assert repo.get_asset(gone) is None


def test_concurrent_restores_and_purges_never_leave_a_photo_without_its_original(world) -> None:  # type: ignore[no-untyped-def]
    import threading

    repo, store, _, trash = world
    ids = [library_photo(repo, store, n) for n in range(1, 41)]
    trash.trash(ids, user_id=1)
    start = threading.Barrier(2)

    def purge() -> None:
        start.wait()
        trash.empty(ADMIN, None)

    def restore() -> None:
        start.wait()
        for asset_id in ids:
            trash.restore([asset_id])

    threads = [threading.Thread(target=purge), threading.Thread(target=restore)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for n, asset_id in enumerate(ids, start=1):
        asset = repo.get_asset(asset_id)
        if asset is None:
            assert repo.is_purged_hash(new_asset(n).content_hash)
            continue
        assert store.absolute(asset.library_path).is_file(), f"photo {n} lost its original"


class CountedIds(list[int]):
    iterations = 0

    def __iter__(self):  # type: ignore[no-untyped-def]
        self.iterations += 1
        return super().__iter__()


def test_emptying_reads_the_wanted_ids_once_however_many_photos_are_in_the_trash(world) -> None:  # type: ignore[no-untyped-def]
    repo, store, _, trash = world
    ids = [library_photo(repo, store, n) for n in range(1, 6)]
    trash.trash(ids, user_id=1)
    wanted = CountedIds(ids[:2])
    assert trash.empty(ADMIN, wanted) == 2
    assert wanted.iterations == 1, "not once per photo in the trash"


class OneStuckFile:
    """The store, except that one photo's original cannot be deleted."""

    def __init__(self, store: DiskLibraryStore, stuck: str) -> None:
        self._store = store
        self._stuck = stuck

    def remove(self, relative_path: str) -> None:
        if relative_path == self._stuck:
            raise PermissionError(13, "Permission denied", relative_path)
        self._store.remove(relative_path)

    def remove_renditions(self, content_hash: str) -> None:
        self._store.remove_renditions(content_hash)


def test_one_file_that_cannot_be_deleted_does_not_stop_the_purge(world, caplog) -> None:  # type: ignore[no-untyped-def]
    repo, store, clock, _ = world
    stuck, fine = library_photo(repo, store, 1), library_photo(repo, store, 2)
    stuck_asset, fine_asset = repo.get_asset(stuck), repo.get_asset(fine)
    assert stuck_asset is not None and fine_asset is not None
    trash = Trash(repo, OneStuckFile(store, stuck_asset.library_path), clock)
    trash.trash([stuck, fine], user_id=1)
    with caplog.at_level("WARNING"):
        assert trash.empty(ADMIN, None) == 2
    assert repo.get_asset(stuck) is None and repo.get_asset(fine) is None
    assert not store.absolute(fine_asset.library_path).exists()
    assert not store.absolute("derived/thumb/1.webp").exists(), "the rest of it still goes"
    (warning,) = [r for r in caplog.records if r.levelname == "WARNING"]
    assert getattr(warning, "path", None) == stuck_asset.library_path
