"""Acceptance tests for M1 import (docs/ROADMAP.md, M1 acceptance).

Real ExifTool + libvips + SQLite against the synthetic fixture set. The ``source_guard``
fixture fails any test that changes a single byte or timestamp in a source folder.
"""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.exiftool_reader import ExifToolReader
from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore, FolderSourceReader
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.app.import_source import ImportSettings, ImportSource, SourceUnavailableError
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.model import Outcome, RunStatus
from tests.factories import NOW
from tests.fixtures.expected import DUPLICATE, FAILED, IGNORED, IMPORTED, SKIPPED, TOTAL_FILES

pytestmark = pytest.mark.integration


class FixedClock:
    def now(self) -> datetime:
        return NOW


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
    repo = SqliteRepository(open_database(":memory:"))
    store = DiskLibraryStore(data)
    importer = ImportSource(
        repo=repo,
        reader=FolderSourceReader(),
        hasher=Blake3Hasher(),
        metadata=exiftool,
        renderer=VipsRenderer(),
        store=store,
        clock=FixedClock(),
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
