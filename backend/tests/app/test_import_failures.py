"""Failure paths of ImportSource, driven with small fakes (no external tools)."""

from datetime import datetime
from pathlib import Path

from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore, FolderSourceReader
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.import_source import ImportSettings, ImportSource
from photo_assistant.domain.capture_time import MetadataDates
from photo_assistant.domain.model import Outcome, PhotoMetadata
from tests.factories import NOW


class Clock:
    def now(self) -> datetime:
        return NOW


class GoodMetadata:
    def read_many(self, paths: list[Path]) -> list[PhotoMetadata]:
        return [
            PhotoMetadata(MetadataDates("2020:01:01 10:00:00"), 10, 10, mime_type="image/jpeg")
            for _ in paths
        ]


class FakeRenderer:
    def __init__(self, fail_for: str = "") -> None:
        self.fail_for = fail_for

    def render(self, source: Path, destination: Path, max_edge: int) -> tuple[int, int]:
        if self.fail_for and self.fail_for in source.name:
            raise RuntimeError("VipsJpeg: bad data\nPremature end of JPEG file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"webp")
        return 10, 10


class UnreadableHasher(Blake3Hasher):
    def hash_file(self, path: Path) -> str:
        if "locked" in path.name:
            raise PermissionError(13, "Permission denied")
        return super().hash_file(path)


class BrokenDiskStore(DiskLibraryStore):
    def store_original(self, source_file: Path, relative_path: str, content_hash: str) -> None:
        raise OSError(28, "No space left on device")


def build(tmp_path: Path, **overrides: object) -> tuple[SqliteRepository, ImportSource, Path]:
    folder = tmp_path / "src"
    folder.mkdir()
    repo = SqliteRepository(open_database(":memory:"))
    parts: dict[str, object] = {
        "repo": repo,
        "reader": FolderSourceReader(),
        "hasher": Blake3Hasher(),
        "metadata": GoodMetadata(),
        "renderer": FakeRenderer(),
        "store": DiskLibraryStore(tmp_path / "data"),
        "clock": Clock(),
        "settings": ImportSettings(min_free_bytes=0),
    }
    parts.update(overrides)
    return repo, ImportSource(**parts), folder  # type: ignore[arg-type]


def test_unreadable_file_fails_with_reason_and_others_continue(tmp_path: Path) -> None:
    repo, importer, folder = build(tmp_path, hasher=UnreadableHasher())
    (folder / "locked.jpg").write_bytes(b"a")
    (folder / "ok.jpg").write_bytes(b"b")
    _, report = importer.run(repo.add_source("s", str(folder)).id)
    by_path = {i.relative_path: i for i in report.items}
    assert by_path["locked.jpg"].outcome is Outcome.FAILED
    assert "Permission denied" in (by_path["locked.jpg"].reason or "")
    assert by_path["ok.jpg"].outcome is Outcome.IMPORTED


def test_failed_copy_leaves_no_thumbnail_or_asset(tmp_path: Path) -> None:
    store = BrokenDiskStore(tmp_path / "data")
    repo, importer, folder = build(tmp_path, store=store)
    (folder / "a.jpg").write_bytes(b"a")
    _, report = importer.run(repo.add_source("s", str(folder)).id)
    (item,) = report.items
    assert item.outcome is Outcome.FAILED and "No space left" in (item.reason or "")
    assert repo.count_assets() == 0
    assert not list((tmp_path / "data").rglob("*.webp"))


def test_copy_of_a_file_that_failed_to_decode_fails_too(tmp_path: Path) -> None:
    repo, importer, folder = build(tmp_path, renderer=FakeRenderer(fail_for="bad"))
    (folder / "bad.jpg").write_bytes(b"same")
    (folder / "bad copy.jpg").write_bytes(b"same")
    _, report = importer.run(repo.add_source("s", str(folder)).id)
    reasons = {i.relative_path: i.reason for i in report.items}
    assert all(i.outcome is Outcome.FAILED for i in report.items)
    assert "Premature end of JPEG file" in (reasons["bad copy.jpg"] or reasons["bad.jpg"] or "")
    assert any("which failed" in (r or "") for r in reasons.values())


def test_low_disk_mid_run_skips_the_rest_and_their_copies(tmp_path: Path) -> None:
    class ShrinkingStore(DiskLibraryStore):
        calls = 0

        def free_bytes(self) -> int:
            ShrinkingStore.calls += 1
            return 10**12 if ShrinkingStore.calls == 1 else 0

    repo, importer, folder = build(
        tmp_path,
        store=ShrinkingStore(tmp_path / "data"),
        settings=ImportSettings(min_free_bytes=1),
    )
    (folder / "a.jpg").write_bytes(b"a")
    (folder / "b.jpg").write_bytes(b"b")
    (folder / "b again.jpg").write_bytes(b"b")
    _, report = importer.run(repo.add_source("s", str(folder)).id)
    outcomes = {i.relative_path: i.outcome for i in report.items}
    assert outcomes["a.jpg"] is Outcome.IMPORTED
    assert outcomes["b.jpg"] is Outcome.SKIPPED
    assert outcomes["b again.jpg"] is Outcome.SKIPPED
    assert report.files_seen == 3
