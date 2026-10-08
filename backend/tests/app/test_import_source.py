"""Acceptance tests for M1 import (docs/ROADMAP.md, M1 acceptance).

Real ExifTool + libvips + SQLite against the synthetic fixture set. The ``source_guard``
fixture fails any test that changes a single byte or timestamp in a source folder.
"""

import os
import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.exiftool_reader import ExifToolReader
from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore, FolderSourceReader
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.app.import_source import ImportSettings, ImportSource, SourceUnavailableError
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.model import Outcome, RunStatus
from photo_assistant.ports import ImportBusyError
from tests.fakes import FakeClock
from tests.fixtures.expected import DUPLICATE, FAILED, IGNORED, IMPORTED, SKIPPED, TOTAL_FILES

pytestmark = pytest.mark.integration


@dataclass
class World:
    repo: SqliteRepository
    store: DiskLibraryStore
    importer: ImportSource
    data: Path


@pytest.fixture(scope="module")
def exiftool() -> Iterator[ExifToolReader]:
    reader = ExifToolReader()
    yield reader
    reader.close()


def make_world(data: Path, exiftool: ExifToolReader, **settings: int) -> World:
    repo = SqliteRepository(Database.open(":memory:"))
    store = DiskLibraryStore(data)
    importer = ImportSource(
        repo=repo,
        reader=FolderSourceReader(),
        hasher=Blake3Hasher(),
        metadata=exiftool,
        renderer=VipsRenderer(),
        store=store,
        clock=FakeClock(),
        settings=ImportSettings(**settings),
    )
    return World(repo, store, importer, data)


@pytest.fixture
def world(tmp_path: Path, exiftool: ExifToolReader) -> World:
    return make_world(tmp_path / "data", exiftool, min_free_bytes=0)


def outcomes(report_items: list, outcome: Outcome) -> set[str]:  # type: ignore[type-arg]
    return {i.relative_path for i in report_items if i.outcome is outcome}


def test_first_import_sorts_every_file_into_exactly_one_outcome(
    world: World, source_guard: Path
) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    _, report = world.importer.run(source.id)

    assert report.status is RunStatus.DONE
    assert outcomes(report.items, Outcome.IMPORTED) == IMPORTED
    assert outcomes(report.items, Outcome.DUPLICATE) == DUPLICATE
    assert outcomes(report.items, Outcome.SKIPPED) == SKIPPED
    assert outcomes(report.items, Outcome.FAILED) == FAILED
    assert report.ignored == IGNORED
    assert report.files_seen == TOTAL_FILES, (
        "files seen = imported + dup + skipped + failed + ignored"
    )
    assert world.repo.count_assets() == len(IMPORTED)


def test_every_failure_and_skip_explains_itself(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    _, report = world.importer.run(source.id)
    reasons = {
        i.relative_path: i.reason
        for i in report.items
        if i.outcome in (Outcome.FAILED, Outcome.SKIPPED)
    }
    assert all(reasons.values()), reasons
    assert "empty" in (reasons["empty.jpg"] or "")
    assert "video" in (reasons["IMG_1003.MOV"] or "")
    assert "Live Photo" in (reasons["IMG_1004.MOV"] or "")
    assert "pdf" in (reasons["Trip.pdf"] or "")


def test_second_run_changes_nothing(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    files_before = sorted(p.relative_to(world.data) for p in world.data.rglob("*") if p.is_file())

    _, again = world.importer.run(source.id)

    assert again.count(Outcome.IMPORTED) == 0
    assert again.count(Outcome.ALREADY_KNOWN) == len(IMPORTED) + len(DUPLICATE)
    assert world.repo.count_assets() == len(IMPORTED)
    files_after = sorted(p.relative_to(world.data) for p in world.data.rglob("*") if p.is_file())
    assert files_after == files_before


def test_overlapping_sources_are_aggregated_without_duplicates(
    world: World, source_guard: Path, tmp_path: Path
) -> None:
    second = tmp_path / "old-hdd"
    second.mkdir()
    shutil.copy2(source_guard / "IMG_1001.JPG", second / "holiday.jpg")  # same photo, new name
    shutil.copy2(source_guard / "IMG_1002.JPG", second / "IMG_1002.JPG")
    a = world.repo.add_source("Laptop", str(source_guard))
    b = world.repo.add_source("Old HDD", str(second))

    world.importer.run(a.id)
    _, report_b = world.importer.run(b.id)

    assert report_b.count(Outcome.IMPORTED) == 0
    assert report_b.count(Outcome.DUPLICATE) == 2
    asset_id = world.repo.asset_id_for_source_path(a.id, "IMG_1001.JPG")
    assert world.repo.asset_id_for_source_path(b.id, "holiday.jpg") == asset_id


def test_originals_are_copied_verified_and_thumbnails_exist(
    world: World, source_guard: Path
) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    for asset in world.repo.list_assets(limit=100).items:
        original = world.store.absolute(asset.library_path)
        assert Blake3Hasher().hash_file(original) == asset.content_hash
        assert asset.library_path.startswith("originals/")
        assert asset.thumb_path is not None and world.store.absolute(asset.thumb_path).is_file()


def test_capture_time_sources_follow_the_fallback_chain(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)

    def asset_for(path: str):  # type: ignore[no-untyped-def]
        asset_id = world.repo.asset_id_for_source_path(source.id, path)
        assert asset_id is not None, path
        asset = world.repo.get_asset(asset_id)
        assert asset is not None
        return asset

    exif = asset_for("IMG_1001.JPG")
    assert (exif.taken_at, exif.tz_offset_minutes, exif.date_source) == (
        datetime(2019, 7, 4, 18, 30),
        120,
        DateSource.EXIF,
    )
    assert asset_for("IMG_20180312_091500.jpg").date_source is DateSource.FILENAME
    heic = asset_for("IMG_1004.HEIC")
    assert (heic.taken_at, heic.camera_model) == (datetime(2021, 8, 15, 9, 5), "iPhone 12")
    assert heic.thumb_path is not None and (heic.width, heic.height) == (96, 64)
    assert asset_for("Screenshot from 2026-07-03 15-21-27.png").date_source is DateSource.FILENAME
    assert asset_for("nested/no-exif.jpg").date_source is DateSource.FILE_MTIME
    rotated = asset_for("IMG_1002.JPG")
    assert (rotated.width, rotated.height) == (120, 160), "stored as displayed"
    assert exif.latitude is not None and exif.camera_model == "iPhone 8"


def test_iphone_edit_is_linked_to_its_original(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    original = world.repo.asset_id_for_source_path(source.id, "IMG_1001.JPG")
    edit_id = world.repo.asset_id_for_source_path(source.id, "IMG_E1001.JPG")
    assert edit_id is not None
    edit = world.repo.get_asset(edit_id)
    assert edit is not None and edit.variant_of == original


def test_each_import_queues_a_preview_job(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    jobs = world.repo.list_jobs("queued")
    assert len(jobs) == len(IMPORTED)
    assert {j["kind"] for j in jobs} == {"preview"}


def test_low_disk_pauses_before_copying_anything(
    tmp_path: Path, source_guard: Path, exiftool: ExifToolReader
) -> None:
    world = make_world(tmp_path / "data", exiftool, min_free_bytes=10**18)
    source = world.repo.add_source("Fixtures", str(source_guard))
    _, report = world.importer.run(source.id)
    assert report.status is RunStatus.PAUSED_LOW_DISK
    assert report.message and "free" in report.message
    assert world.repo.count_assets() == 0
    assert not (tmp_path / "data" / "originals").exists()


def test_a_source_that_contains_the_library_is_refused_at_scan_time(
    world: World, tmp_path: Path
) -> None:
    """The library folder may be configured after the source was added."""
    outer = world.repo.add_source("Everything", str(tmp_path))
    with pytest.raises(SourceUnavailableError, match="library"):
        world.importer.run(outer.id)


def test_edit_pairing_ignores_extension_case(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "IMG_2001.JPG")
    shutil.copy2(fixtures / "IMG_E1001.JPG", folder / "IMG_E2001.jpg")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    edit = world.repo.get_asset(
        world.repo.asset_id_for_source_path(source.id, "IMG_E2001.jpg") or 0
    )
    assert edit is not None
    assert edit.variant_of == world.repo.asset_id_for_source_path(source.id, "IMG_2001.JPG")


def _variant_of(world: World, source_id: int, path: str) -> int | None:
    asset = world.repo.get_asset(world.repo.asset_id_for_source_path(source_id, path) or 0)
    assert asset is not None, path
    return asset.variant_of


def test_a_jpeg_edit_is_linked_to_its_heic_original(world: World, tmp_path: Path) -> None:
    """What an iPhone really exports: IMG_1234.HEIC and the edit as IMG_E1234.JPG."""
    folder = tmp_path / "src"
    (folder / "other").mkdir(parents=True)
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1004.HEIC", folder / "IMG_2004.HEIC")
    shutil.copy2(fixtures / "IMG_E1001.JPG", folder / "IMG_E2004.JPG")
    shutil.copy2(fixtures / "IMG_1004.MOV", folder / "IMG_2005.MOV")  # a video is no original
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "IMG_E2005.JPG")
    shutil.copy2(fixtures / "IMG_1002.JPG", folder / "other" / "IMG_2006.JPG")  # other folder
    shutil.copy2(fixtures / "IMG_20180312_091500.jpg", folder / "IMG_E2006.JPG")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    original = world.repo.asset_id_for_source_path(source.id, "IMG_2004.HEIC")
    assert original is not None
    assert _variant_of(world, source.id, "IMG_E2004.JPG") == original
    assert _variant_of(world, source.id, "IMG_E2005.JPG") is None
    assert _variant_of(world, source.id, "IMG_E2006.JPG") is None


def test_an_edit_prefers_the_original_with_its_own_extension(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1004.HEIC", folder / "IMG_2001.HEIC")
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "IMG_2001.JPG")
    shutil.copy2(fixtures / "IMG_E1001.JPG", folder / "IMG_E2001.JPG")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    same_extension = world.repo.asset_id_for_source_path(source.id, "IMG_2001.JPG")
    assert _variant_of(world, source.id, "IMG_E2001.JPG") == same_extension


def test_an_edit_added_later_is_linked_to_an_original_imported_before(
    world: World, tmp_path: Path
) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1004.HEIC", folder / "IMG_2004.HEIC")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    shutil.copy2(fixtures / "IMG_E1001.JPG", folder / "IMG_E2004.JPG")
    world.importer.run(source.id)
    original = world.repo.asset_id_for_source_path(source.id, "IMG_2004.HEIC")
    assert original is not None
    assert _variant_of(world, source.id, "IMG_E2004.JPG") == original


def test_missing_or_disabled_source_is_refused(world: World, tmp_path: Path) -> None:
    gone = world.repo.add_source("Unplugged disk", str(tmp_path / "not-mounted"))
    with pytest.raises(SourceUnavailableError, match="not found"):
        world.importer.run(gone.id)
    with pytest.raises(SourceUnavailableError, match="no source"):
        world.importer.run(999)
    world.repo.set_source_enabled(gone.id, False)
    with pytest.raises(SourceUnavailableError, match="disabled"):
        world.importer.run(gone.id)


def test_report_is_saved_and_retrievable(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    run_id, report = world.importer.run(source.id)
    saved = world.repo.get_import_report(run_id)
    assert saved is not None and saved.summary() == report.summary()


def test_a_file_changed_in_place_is_imported_again_and_relinked(
    world: World, tmp_path: Path
) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "photo.jpg")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    first = world.repo.asset_id_for_source_path(source.id, "photo.jpg")

    shutil.copy2(fixtures / "IMG_1002.JPG", folder / "photo.jpg")  # edited elsewhere, same name
    _, report = world.importer.run(source.id)

    assert report.count(Outcome.IMPORTED) == 1
    second = world.repo.asset_id_for_source_path(source.id, "photo.jpg")
    assert second not in (None, first)
    assert world.repo.get_asset(first or 0) is not None, "the earlier version is kept"


@pytest.mark.parametrize(
    "evil_name",
    ["x\n-overwrite_original\n-all=\ny.jpg", "tab\there.jpg", "cr\r-all=.jpg"],
)
def test_file_names_with_control_characters_never_reach_exiftool(
    world: World, tmp_path: Path, evil_name: str
) -> None:
    """Regression (QA M1): a newline in a name became extra ExifTool options that
    rewrote other photos in the source folder."""
    from tests.conftest import snapshot_tree

    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "a.jpg")
    shutil.copy2(fixtures / "IMG_1002.JPG", folder / evil_name)
    before = snapshot_tree(folder)

    _, report = world.importer.run(world.repo.add_source("s", str(folder)).id)

    assert snapshot_tree(folder) == before, "source folder must be untouched"
    by_path = {i.relative_path: i for i in report.items}
    assert by_path["a.jpg"].outcome is Outcome.IMPORTED
    assert by_path[evil_name].outcome is Outcome.FAILED
    assert "file name" in (by_path[evil_name].reason or "")


def test_rerun_repairs_a_photo_left_without_thumbnail_by_a_crash(
    world: World, source_guard: Path
) -> None:
    """Regression (QA M1): a crash between DB writes left photos broken forever."""
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    asset_id = world.repo.asset_id_for_source_path(source.id, "IMG_1001.JPG")
    assert asset_id is not None
    world.repo._conn.execute("UPDATE asset SET thumb_path = NULL WHERE id = ?", (asset_id,))
    world.repo._conn.execute("DELETE FROM job")

    world.importer.run(source.id)

    asset = world.repo.get_asset(asset_id)
    assert asset is not None and asset.thumb_path is not None
    assert world.store.absolute(asset.thumb_path).is_file()
    assert {j["payload"]["asset_id"] for j in world.repo.list_jobs("queued")} == {asset_id}


def test_only_one_import_runs_at_a_time_per_library(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    with world.store.exclusive_import(), pytest.raises(ImportBusyError, match="already running"):
        world.importer.run(source.id)
    world.importer.run(source.id)  # lock released


def test_a_crash_mid_run_still_saves_what_happened(
    tmp_path: Path, source_guard: Path, exiftool: ExifToolReader
) -> None:
    class DyingMetadata:
        def read_many(self, paths: list[Path]) -> list[object]:
            raise RuntimeError("exiftool died")

    world = make_world(tmp_path / "data", exiftool, min_free_bytes=0)
    world.importer._metadata = DyingMetadata()  # type: ignore[assignment]
    source = world.repo.add_source("Fixtures", str(source_guard))
    with pytest.raises(RuntimeError, match="exiftool died"):
        world.importer.run(source.id)
    (run,) = world.repo.list_import_runs(source.id)
    assert run["status"] == "failed"
    assert "exiftool died" in str(run["message"])


class CountingHasher(Blake3Hasher):
    def __init__(self) -> None:
        self.calls = 0

    def hash_file(self, path: Path) -> str:
        self.calls += 1
        return super().hash_file(path)


def test_rescan_skips_hashing_files_that_have_not_changed(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    counting = CountingHasher()
    world.importer._hasher = counting

    _, report = world.importer.run(source.id)

    assert report.count(Outcome.ALREADY_KNOWN) == len(IMPORTED) + len(DUPLICATE)
    assert counting.calls == len(FAILED) - 1, (
        "only never-imported files are hashed (empty.jpg isn't)"
    )


def test_touched_file_is_rehashed_but_still_known(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    photo = folder / "a.jpg"
    shutil.copy2(Path(__file__).parent.parent / "fixtures" / "photos" / "IMG_1001.JPG", photo)
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    photo.touch()  # mtime changes, content does not
    counting = CountingHasher()
    world.importer._hasher = counting
    _, report = world.importer.run(source.id)
    assert counting.calls == 1
    assert report.items[0].outcome is Outcome.ALREADY_KNOWN


def test_renamed_file_says_where_it_was_before(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "old name.jpg")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    (folder / "old name.jpg").rename(folder / "new name.jpg")
    _, report = world.importer.run(source.id)
    (item,) = report.items
    assert item.outcome is Outcome.DUPLICATE
    assert "old name.jpg" in (item.reason or "")


def test_changed_file_reports_that_the_old_version_is_kept(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "p.jpg")
    source = world.repo.add_source("s", str(folder))
    world.importer.run(source.id)
    shutil.copy2(fixtures / "IMG_1002.JPG", folder / "p.jpg")
    _, report = world.importer.run(source.id)
    (item,) = report.items
    assert item.outcome is Outcome.IMPORTED
    assert "previous version kept" in (item.reason or "")


# --- QA M1, second review ------------------------------------------------------------------


def test_non_utf8_file_name_fails_alone_and_the_rest_imports(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "good.jpg")
    bad = Path(os.fsdecode(os.fsencode(folder) + b"/bad-\xff\xfe.jpg"))  # not valid UTF-8
    bad.write_bytes((fixtures / "IMG_1002.JPG").read_bytes())

    _, report = world.importer.run(world.repo.add_source("old usb disk", str(folder)).id)

    outcomes = {i.relative_path: (i.outcome, i.reason) for i in report.items}
    assert outcomes["good.jpg"][0] is Outcome.IMPORTED
    (bad_name,) = [p for p in outcomes if p != "good.jpg"]
    assert outcomes[bad_name][0] is Outcome.FAILED
    assert "UTF-8" in (outcomes[bad_name][1] or "")
    bad_name.encode("utf-8")  # stored name is printable and valid


def test_safe_copy_of_an_unsafe_named_file_still_imports(world: World, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    fixtures = Path(__file__).parent.parent / "fixtures" / "photos"
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "A\ttab.jpg")  # sorts first, fails
    shutil.copy2(fixtures / "IMG_1001.JPG", folder / "b-fine.jpg")
    _, report = world.importer.run(world.repo.add_source("s", str(folder)).id)
    outcomes = {i.relative_path: i.outcome for i in report.items}
    assert outcomes["b-fine.jpg"] is Outcome.IMPORTED
    assert outcomes["A\ttab.jpg"] is Outcome.FAILED


def test_replaced_file_with_same_size_and_restored_mtime_is_noticed(
    world: World, tmp_path: Path
) -> None:
    """cp -p / rsync -t can restore mtime; the change time (ctime) can't be restored."""
    folder = tmp_path / "src"
    folder.mkdir()
    photo = folder / "p.jpg"
    photo.write_bytes(b"A" * 1000)
    source = world.repo.add_source("s", str(folder))
    world.importer._metadata = _FakeMeta()  # type: ignore[assignment]
    world.importer._renderer = _FakeRenderer()  # type: ignore[assignment]
    world.importer.run(source.id)
    stat = photo.stat()
    time.sleep(0.01)
    photo.write_bytes(b"B" * 1000)
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    _, report = world.importer.run(source.id)
    assert report.items[0].outcome is Outcome.IMPORTED


def test_repair_that_fails_does_not_stop_the_import(world: World, source_guard: Path) -> None:
    source = world.repo.add_source("Fixtures", str(source_guard))
    world.importer.run(source.id)
    asset_id = world.repo.asset_id_for_source_path(source.id, "IMG_1001.JPG")
    world.repo._conn.execute("UPDATE asset SET thumb_path = NULL WHERE id = ?", (asset_id,))
    world.importer._renderer = _FakeRenderer(fail=True)  # type: ignore[assignment]
    _, report = world.importer.run(source.id)
    assert report.status is RunStatus.DONE


class _FakeMeta:
    def read_many(self, paths: list[Path]) -> list[object]:
        from photo_assistant.domain.model import PhotoMetadata

        return [PhotoMetadata(width=1, height=1, mime_type="image/jpeg") for _ in paths]


class _FakeRenderer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        if self.fail:
            raise RuntimeError("decoder broke")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"x")
        return 1, 1
