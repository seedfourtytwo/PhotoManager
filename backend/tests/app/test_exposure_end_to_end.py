"""Exposure settings through the real services: ExifTool, the importer, the job queue.

Synthetic photos only. No file may change: not in the source folder, not in the library.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.api.services import Services, build_services
from photo_assistant.app.exposure_backfill import EXPOSURE_BACKFILL_JOB
from photo_assistant.domain.exposure import Exposure
from tests.conftest import snapshot_tree
from tests.library_builder import settings_for
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

SHOTS = {
    "day.jpg": Exposure(f_number=8.0, exposure_time=1 / 500, iso=100, focal_length=24.0),
    "night.jpg": Exposure(f_number=1.8, exposure_time=2.5, iso=3200, focal_length=4.25),
    "old-camera.jpg": Exposure(iso=200),
    "scan.jpg": Exposure(),
}


@pytest.fixture
def source(tmp_path: Path) -> Iterator[Path]:
    """A folder of synthetic photos that must be byte-identical when the test ends."""
    folder = tmp_path / "pictures"
    for seed, (name, exposure) in enumerate(SHOTS.items(), start=1):
        write_photo(folder / name, seed=seed, exposure=None if exposure.is_empty else exposure)
    before = snapshot_tree(folder)
    yield folder
    assert snapshot_tree(folder) == before, "a source folder was modified"


@pytest.fixture
def services(tmp_path: Path, source: Path) -> Iterator[Services]:
    """A library with the source imported and every follow-up job done."""
    built = build_services(settings_for(tmp_path / "data"))
    try:
        added = built.repo.add_source("Pictures", str(source))
        built.importer.run(added.id)
        built.worker.run_until_idle()
        yield built
    finally:
        built.close()


def stored(services: Services) -> dict[str, Exposure]:
    (source,) = services.repo.list_sources()
    found = {}
    for name in SHOTS:
        asset_id = services.repo.asset_id_for_source_path(source.id, name)
        assert asset_id is not None, name
        asset = services.repo.get_asset(asset_id)
        assert asset is not None
        found[name] = asset.exposure
    return found


def forget_exposure(services: Services) -> None:
    """Make the library look as one imported before migration 0028 does."""
    with services.db.transaction() as conn:
        conn.execute(
            "UPDATE asset SET f_number = NULL, exposure_time = NULL, iso = NULL, "
            "focal_length = NULL"
        )


def test_an_import_stores_the_exposure_each_new_photo_carries(services: Services) -> None:
    assert stored(services) == SHOTS


def test_the_backfill_job_fills_an_older_library_from_its_own_copies_and_changes_no_file(
    services: Services, tmp_path: Path
) -> None:
    forget_exposure(services)
    assert stored(services) == dict.fromkeys(SHOTS, Exposure())
    originals = snapshot_tree(tmp_path / "data" / "originals")

    assert services.repo.enqueue_once(EXPOSURE_BACKFILL_JOB) is not None
    services.worker.run_until_idle()

    assert stored(services) == SHOTS
    assert snapshot_tree(tmp_path / "data" / "originals") == originals, "a library original changed"
    assert services.repo.list_jobs("failed") == []


def test_the_backfill_never_reads_a_source_folder(services: Services, source: Path) -> None:
    """With the source folder gone the values still come back: from the library copy."""
    forget_exposure(services)
    hidden = source.rename(source.with_name("unplugged"))
    try:
        services.repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
        services.worker.run_until_idle()
        assert stored(services) == SHOTS
    finally:
        hidden.rename(source)
