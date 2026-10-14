"""Stop watching a folder: the source goes, its photos stay or go to the trash, the folder on
disk is never touched (that is the API test's job: here nothing even knows where it is)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.stop_watching import (
    InboxNotRemovableError,
    KeptSourceError,
    PhotosOnlyHere,
    Removal,
    Removed,
    SourceNotFoundError,
    StopWatching,
    only_from,
)
from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.domain.access import INBOX_KIND, KEPT_KIND, Role, SourceAccess
from photo_assistant.domain.errors import ConflictError, InvalidError, NotFoundError
from photo_assistant.domain.model import ImportReport, Source
from photo_assistant.domain.recheck import Recheck
from photo_assistant.ports import ImportBusyError, SourceBusyError
from tests.factories import NOW, new_asset
from tests.fakes import FakeClock


class FakeImportLock:
    def __init__(self) -> None:
        self.busy = False
        self.held = False

    @contextmanager
    def exclusive_import(self) -> Iterator[None]:
        if self.busy:
            raise ImportBusyError("an import into this library is already running")
        self.held = True
        try:
            yield
        finally:
            self.held = False


class FakeStaging:
    def __init__(self) -> None:
        self.removed: list[int] = []
        self.fails = False

    def remove(self, source_id: int) -> None:
        if self.fails:
            raise PermissionError("not allowed")
        self.removed.append(source_id)


class World:
    def __init__(self, repo: SqliteRepository) -> None:
        self.repo = repo
        self.admin = repo.add_user("c", "C", "hash", Role.ADMIN).id
        self.lock = FakeImportLock()
        self.staging = FakeStaging()
        self.clock = FakeClock()
        self.use = StopWatching(repo, self.lock, self.staging, self.clock)
        self.folder = repo.add_source("Old disk", "/media/old", owner_id=self.admin).id
        self.other = repo.add_source("Laptop", "/home/c/Pictures", owner_id=self.admin).id

    def photo(self, n: int, *sources: int) -> int:
        asset_id = self.repo.add_asset(new_asset(n), NOW)
        for source_id in sources:
            self.repo.add_asset_source(asset_id, source_id, f"{n}.jpg")
        return asset_id

    def trashed(self) -> dict[int, int | None]:
        rows = self.repo._all("SELECT id, trashed_by FROM asset WHERE trashed_at IS NOT NULL")
        return {int(r["id"]): r["trashed_by"] for r in rows}

    def count(self, sql: str, *params: object) -> int:
        row = self.repo._one(sql, params)
        assert row is not None
        return int(row[0])


@pytest.fixture
def world(repo: SqliteRepository) -> World:
    return World(repo)


# --- which photos come only from the folder ------------------------------------------------


def test_only_from_keeps_the_photos_no_other_source_holds() -> None:
    holdings = {1: frozenset({7}), 2: frozenset({7, 8}), 3: frozenset({7}), 4: frozenset({8})}
    assert only_from(7, holdings) == [1, 3]


def test_only_from_an_empty_folder_is_nothing() -> None:
    assert only_from(7, {}) == []


def test_the_preview_counts_every_photo_and_those_found_only_here(world: World) -> None:
    world.photo(1, world.folder)
    world.photo(2, world.folder, world.other)
    world.photo(3, world.other)
    assert world.use.preview(world.folder) == Removal(photos=2, only_here=1)
    assert world.use.preview(world.other) == Removal(photos=2, only_here=1)


def test_the_preview_leaves_out_photos_already_in_the_trash(world: World) -> None:
    gone = world.photo(1, world.folder)
    world.photo(2, world.folder)
    world.repo.trash_assets([gone], world.admin, NOW)
    assert world.use.preview(world.folder) == Removal(photos=1, only_here=1)


def test_the_preview_of_an_unknown_source_is_not_found(world: World) -> None:
    with pytest.raises(SourceNotFoundError):
        world.use.preview(999)
    assert issubclass(SourceNotFoundError, NotFoundError)


# --- keep: the source is detached, so everyone who sees the photos still does --------------


def _links(world: World, source_id: int) -> tuple[int, int, int]:
    return tuple(  # type: ignore[return-value]
        world.count(f"SELECT COUNT(*) FROM {table} WHERE source_id = ?", source_id)
        for table in ("asset_source", "source_access", "import_run")
    )


def test_keep_detaches_the_source_and_keeps_every_link_to_its_photos(world: World) -> None:
    world.photo(1, world.folder)
    world.photo(2, world.folder, world.other)
    world.repo.save_import_report(ImportReport(source_id=world.folder), NOW, NOW)
    world.repo.set_source_recheck(world.folder, Recheck.DAILY)
    links = _links(world, world.folder)

    removed = world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)

    assert removed == Removed(only_here=1, trashed=0, detached=True)
    kept = world.repo.get_source(world.folder)
    assert kept == Source(
        world.folder,
        "Old disk",
        f"kept:{world.folder}",
        enabled=False,
        kind=KEPT_KIND,
        owner_id=world.admin,
        recheck=Recheck.OFF,
    )
    assert _links(world, world.folder) == links, "access and photos exactly as they were"
    assert world.trashed() == {}


def test_after_keep_the_same_folder_can_be_added_again(world: World) -> None:
    world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)
    again = world.repo.add_source("Old disk", "/media/old", owner_id=world.admin)
    assert again.id != world.folder


def test_removing_a_kept_source_deletes_it_and_every_row_that_points_at_it(
    world: World,
) -> None:
    only = world.photo(1, world.folder)
    shared = world.photo(2, world.folder, world.other)
    world.repo.save_import_report(ImportReport(source_id=world.folder), NOW, NOW)
    world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)

    removed = world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)

    assert removed == Removed(only_here=1, trashed=0, detached=False)
    assert world.repo.get_source(world.folder) is None
    assert _links(world, world.folder) == (0, 0, 0)
    assert world.count("SELECT COUNT(*) FROM asset WHERE first_source_id = ?", world.folder) == 0
    assert world.trashed() == {}, "kept photos stay in the library"
    assert world.count("SELECT COUNT(*) FROM asset WHERE id IN (?, ?)", only, shared) == 2
    rows = world.repo._all("SELECT source_id FROM asset_source WHERE asset_id = ?", (shared,))
    assert [r["source_id"] for r in rows] == [world.other]


def test_a_kept_source_can_also_be_removed_with_its_photos_to_the_trash(world: World) -> None:
    only = world.photo(1, world.folder)
    world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)
    removed = world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)
    assert removed == Removed(only_here=1, trashed=1, detached=False)
    assert world.trashed() == {only: world.admin}
    assert world.repo.get_source(world.folder) is None


def test_a_kept_source_cannot_be_watched_again(world: World) -> None:
    world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)
    with pytest.raises(KeptSourceError):
        world.use.require_watchable(world.folder)
    world.use.require_watchable(world.other)
    assert issubclass(KeptSourceError, InvalidError)


# --- trash ------------------------------------------------------------------------------


def test_trash_moves_only_the_photos_found_nowhere_else_and_says_who(world: World) -> None:
    only = world.photo(1, world.folder)
    world.photo(2, world.folder, world.other)
    world.clock.at = datetime(2026, 10, 1, 9, 0, tzinfo=NOW.tzinfo)

    removed = world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)

    assert removed == Removed(only_here=1, trashed=1, detached=False)
    assert world.repo.get_source(world.folder) is None
    assert world.trashed() == {only: world.admin}
    row = world.repo._one("SELECT trashed_at FROM asset WHERE id = ?", (only,))
    assert row is not None and row["trashed_at"].startswith("2026-10-01T09:00")


def test_a_photo_already_in_the_trash_keeps_who_put_it_there(world: World) -> None:
    member = world.repo.add_user("lea", "Léa", "hash", Role.MEMBER).id
    earlier = world.photo(1, world.folder)
    world.repo.trash_assets([earlier], member, NOW)
    removed = world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)
    assert removed == Removed(only_here=0, trashed=0, detached=False)
    assert world.trashed() == {earlier: member}


def test_trash_handles_a_folder_bigger_than_sqlites_variable_limit(world: World) -> None:
    ids = [world.photo(n, world.folder) for n in range(1, 1201)]
    removed = world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)
    assert removed == Removed(only_here=1200, trashed=1200, detached=False)
    assert set(world.trashed()) == set(ids)


# --- refusals ---------------------------------------------------------------------------


def test_an_upload_inbox_cannot_be_removed(world: World) -> None:
    inbox = world.repo.add_source(
        "Uploads (C)",
        "/data/inbox/1",
        owner_id=world.admin,
        kind=INBOX_KIND,
        access=SourceAccess(None, ()),
    ).id
    with pytest.raises(InboxNotRemovableError):
        world.use.stop(inbox, PhotosOnlyHere.KEEP, world.admin)
    assert issubclass(InboxNotRemovableError, InvalidError)
    assert world.repo.get_source(inbox) is not None


def test_an_unknown_source_is_not_found(world: World) -> None:
    with pytest.raises(SourceNotFoundError):
        world.use.stop(999, PhotosOnlyHere.KEEP, world.admin)


def test_refused_while_a_check_of_the_folder_runs(world: World) -> None:
    world.photo(1, world.folder)
    world.repo.enqueue(SCAN_JOB_KIND, {"source_id": world.folder})
    assert world.repo.claim_next_job(NOW) is not None  # the worker picked it up
    with pytest.raises(SourceBusyError):
        world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)
    assert issubclass(SourceBusyError, ConflictError)
    assert world.repo.get_source(world.folder) is not None
    assert world.trashed() == {}, "nothing changed"


@pytest.mark.parametrize("photos", list(PhotosOnlyHere))
def test_refused_while_any_import_holds_the_library(world: World, photos: PhotosOnlyHere) -> None:
    world.lock.busy = True
    with pytest.raises(SourceBusyError):
        world.use.stop(world.folder, photos, world.admin)
    assert world.repo.get_source(world.folder) == world.repo.list_sources()[0]


def test_keep_is_refused_too_while_a_check_of_the_folder_runs(world: World) -> None:
    world.repo.enqueue(SCAN_JOB_KIND, {"source_id": world.folder})
    assert world.repo.claim_next_job(NOW) is not None
    with pytest.raises(SourceBusyError):
        world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)
    source = world.repo.get_source(world.folder)
    assert source is not None and source.kind == "folder"


def test_a_check_still_waiting_is_cancelled_with_the_folder(world: World) -> None:
    """A queued (or waiting-to-retry) check has nothing left to do once the folder goes;
    refusing would let an unreachable cloud folder block its own removal for hours."""
    world.repo.enqueue(SCAN_JOB_KIND, {"source_id": world.folder})
    kept = world.repo.enqueue(SCAN_JOB_KIND, {"source_id": world.other})
    world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)
    rows = world.repo._all("SELECT id FROM job WHERE kind = ?", (SCAN_JOB_KIND,))
    assert [r["id"] for r in rows] == [kept]


def test_another_folders_running_check_does_not_block(world: World) -> None:
    world.repo.enqueue(SCAN_JOB_KIND, {"source_id": world.other})
    assert world.repo.claim_next_job(NOW) is not None
    world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)
    assert world.repo.get_source(world.folder) is None


def test_the_work_happens_while_holding_the_import_lock(world: World) -> None:
    seen: list[bool] = []
    real = world.repo.remove_source

    def spy(*args: object, **kwargs: object) -> int:
        seen.append(world.lock.held)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    world.repo.remove_source = spy  # type: ignore[method-assign]
    world.use.stop(world.folder, PhotosOnlyHere.TRASH, world.admin)
    assert seen == [True]


# --- the app's own copy of a cloud folder -------------------------------------------------


@pytest.mark.parametrize("kind", ["rclone", "proton"])
def test_a_cloud_folders_staging_copy_is_removed(world: World, kind: str) -> None:
    cloud = world.repo.add_source("Cloud", "/data/staging/9", owner_id=world.admin, kind=kind).id
    world.use.stop(cloud, PhotosOnlyHere.KEEP, world.admin)
    assert world.staging.removed == [cloud]


def test_a_local_folder_has_no_staging_copy_to_remove(world: World) -> None:
    world.use.stop(world.folder, PhotosOnlyHere.KEEP, world.admin)
    assert world.staging.removed == []


def test_a_staging_copy_that_cannot_be_deleted_does_not_undo_the_removal(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    cloud = world.repo.add_source("Cloud", "/data/staging/9", owner_id=world.admin, kind="rclone")
    world.staging.fails = True
    world.use.stop(cloud.id, PhotosOnlyHere.TRASH, world.admin)
    assert world.repo.get_source(cloud.id) is None
    assert "staging" in caplog.text
