"""A remote source end to end: real rclone (local remote), SQLite, ExifTool and libvips."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.exiftool_reader import ExifToolReader
from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore, FolderSourceReader
from photo_assistant.adapters.rclone_sync import RcloneSync
from photo_assistant.adapters.source_area_store import SourceAreaStore
from photo_assistant.adapters.sqlite_integrations import SqliteRemoteSources
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.app.import_source import ImportSettings, ImportSource
from photo_assistant.app.sync_source import SyncSource, add_remote_source
from photo_assistant.domain.model import Outcome
from photo_assistant.ports.sync import SyncOptions
from tests.conftest import snapshot_tree
from tests.fakes import FakeClock

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed"),
]


@pytest.fixture
def exiftool() -> Iterator[ExifToolReader]:
    reader = ExifToolReader()
    yield reader
    reader.close()


def test_pull_then_import_leaves_the_remote_untouched(
    tmp_path: Path, source_guard: Path, exiftool: ExifToolReader
) -> None:
    data = tmp_path / "data"
    config = tmp_path / "rclone.conf"
    config.write_text("[cloud]\ntype = local\n")
    db = Database.open(":memory:")
    repo = SqliteRepository(db)
    store = SourceAreaStore(DiskLibraryStore(data), [data / "staging", data / "inbox"])
    importer = ImportSource(
        repo=repo,
        reader=FolderSourceReader(),
        hasher=Blake3Hasher(),
        metadata=exiftool,
        renderer=VipsRenderer(),
        store=store,
        clock=FakeClock(),
        settings=ImportSettings(min_free_bytes=0),
    )
    remotes, sync = SqliteRemoteSources(db, repo), RcloneSync(config_path=config)
    use_case = SyncSource(
        sources=repo,
        remotes=remotes,
        sync=sync,
        importer=importer,
        reports=repo,
        clock=FakeClock(),
        staging_root=data / "staging",
        options=SyncOptions(tpslimit=0),
    )
    owner = repo.add_first_admin("c", "C", "x")
    source_id = add_remote_source(
        remotes,
        sync,
        data / "staging",
        "Cloud",
        {"remote": "cloud", "path": str(source_guard)},
        owner.id,
    )
    before = snapshot_tree(source_guard)

    outcome = use_case.run(source_id)
    assert outcome.sync is not None and outcome.sync.copied == 13
    assert outcome.report is not None
    assert outcome.report.count(Outcome.IMPORTED) >= 5
    assert repo.count_assets() == outcome.report.count(Outcome.IMPORTED)

    again = use_case.run(source_id)
    assert again.sync is not None and again.sync.copied == 0
    assert again.report is not None and again.report.count(Outcome.IMPORTED) == 0
    assert snapshot_tree(source_guard) == before
