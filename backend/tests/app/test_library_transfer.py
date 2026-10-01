"""Moving the library (ARCHITECTURE §6): portability, export-library and verify-library.

Integration: the real importer builds a library from the synthetic fixtures."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import Blake3Hasher
from photo_assistant.adapters.library_files import LocalFileTree
from photo_assistant.api.ops_services import build_library_transfer
from photo_assistant.api.services import build_services
from photo_assistant.app.library_transfer import (
    IN_PROGRESS_MARKER,
    LibraryTransfer,
    LibraryTransferError,
)
from photo_assistant.ports.backup import AssetFile
from photo_assistant.ports.library_files import CopyResult, LibraryUnreadableError
from tests.conftest import snapshot_tree
from tests.fixtures.expected import IMPORTED
from tests.library_builder import build_library, settings_for

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def built_library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Built once per module; tests copy it before changing anything."""
    base = tmp_path_factory.mktemp("built")
    source = base / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures" / "photos", source)
    build_library(base / "data", source)
    return base / "data"


@pytest.fixture
def laptop(built_library: Path, tmp_path: Path) -> Path:
    root = tmp_path / "laptop" / "data"
    shutil.copytree(built_library, root)
    return root


def _library_files(root: Path) -> dict[str, tuple[str, int, int]]:
    return {
        k: v
        for k, v in snapshot_tree(root).items()
        if k.split("/")[0] in {"originals", "derived", "recipes"} and v[0] != "dir"
    }


def assert_every_asset_resolves(data_root: Path) -> int:
    """Open the library where it now lives with the real services; check every file."""
    services = build_services(settings_for(data_root))
    hasher = Blake3Hasher()
    try:
        page = services.repo.list_assets(limit=1000)
        for asset in page.items:
            original = services.store.absolute(asset.library_path)
            assert original.is_file(), asset.library_path
            assert hasher.hash_file(original) == asset.content_hash
            for derived in (asset.thumb_path, asset.preview_path):
                assert derived is not None, f"asset {asset.id} has no derivative"
                assert services.store.absolute(derived).is_file(), derived
        return len(page.items)
    finally:
        services.close()


def test_a_copied_library_works_in_its_new_place(laptop: Path, tmp_path: Path) -> None:
    """ARCHITECTURE §6 portability rule: moving = copy data/, set the path, start."""
    server = tmp_path / "server" / "srv" / "photos"
    shutil.copytree(laptop, server)
    shutil.rmtree(laptop.parent)  # the old place is gone: nothing may still point at it
    assert assert_every_asset_resolves(server) == len(IMPORTED)


def test_export_copies_verifies_and_opens_on_the_server(laptop: Path, tmp_path: Path) -> None:
    before = _library_files(laptop)
    destination = tmp_path / "usb-disk" / "photo-library"
    messages: list[str] = []
    summary = build_library_transfer().export(laptop, destination, progress=messages.append)
    assert summary.ok, summary.verify
    assert summary.verify is not None and summary.verify.assets_checked == len(IMPORTED)
    assert summary.copied > 0 and summary.already_there == 0 and summary.bytes_copied > 0
    assert not (destination / IN_PROGRESS_MARKER).exists()
    assert any("verifying" in m for m in messages)
    assert _library_files(laptop) == before, "the source library is only read"
    assert _library_files(destination) == before, "same bytes, same permissions, same mtimes"
    assert not (destination / "library.db-wal").exists(), "the snapshot is self-contained"
    assert assert_every_asset_resolves(destination) == len(IMPORTED)


def test_export_without_thumbnails(laptop: Path, tmp_path: Path) -> None:
    destination = tmp_path / "slim"
    summary = build_library_transfer().export(laptop, destination, include_derived=False)
    assert summary.ok
    assert not (destination / "derived").exists()
    report = build_library_transfer().verify(destination)
    assert report.ok and len(report.missing_derived) == 2 * len(IMPORTED)


class FlakyTree(LocalFileTree):
    """Pretends the USB cable was pulled after a few files."""

    def __init__(self, fail_after: int) -> None:
        super().__init__()
        self.left = fail_after

    def copy_verified(self, source: Path, destination: Path) -> CopyResult:
        if self.left == 0:
            raise OSError("device disconnected")
        self.left -= 1
        return super().copy_verified(source, destination)


def test_an_interrupted_export_resumes_where_it_stopped(laptop: Path, tmp_path: Path) -> None:
    destination = tmp_path / "server"
    real = build_library_transfer()
    hasher = Blake3Hasher()
    flaky = LibraryTransfer(FlakyTree(3), hasher, real._snapshot, real._open_index)
    with pytest.raises(OSError, match="disconnected"):
        flaky.export(laptop, destination)
    assert (destination / IN_PROGRESS_MARKER).exists()
    summary = real.export(laptop, destination)
    assert summary.ok and summary.already_there == 3


def test_export_refuses_unsafe_destinations(laptop: Path, tmp_path: Path) -> None:
    transfer = build_library_transfer()
    with pytest.raises(LibraryTransferError, match="outside the library"):
        transfer.export(laptop, laptop / "exports" / "copy")
    with pytest.raises(LibraryTransferError, match="no library"):
        transfer.export(tmp_path / "nothing-here", tmp_path / "x")
    transfer.export(laptop, tmp_path / "done")
    with pytest.raises(LibraryTransferError, match="already holds a library"):
        transfer.export(laptop, tmp_path / "done")


def test_verify_reports_missing_and_corrupt_photos(laptop: Path) -> None:
    originals = sorted(p for p in (laptop / "originals").rglob("*") if p.is_file())
    originals[0].unlink()
    originals[1].chmod(0o644)
    originals[1].write_bytes(b"bit rot")
    thumb = next(p for p in (laptop / "derived" / "thumb").rglob("*") if p.is_file())
    thumb.unlink()
    report = build_library_transfer().verify(laptop)
    assert not report.ok
    assert len(report.missing) == 1 and len(report.corrupt) == 1
    assert report.missing_derived == [thumb.relative_to(laptop).as_posix()]
    text = "\n".join(report.lines())
    assert "missing" in text and "corrupt" in text and originals[0].name in text


def test_verify_needs_a_library(tmp_path: Path) -> None:
    with pytest.raises(LibraryUnreadableError):
        build_library_transfer().verify(tmp_path)
    (tmp_path / "library.db").write_bytes(b"garbage" * 1000)
    with pytest.raises(LibraryUnreadableError):
        build_library_transfer().verify(tmp_path)


class ListIndex:
    def __init__(self, assets: list[AssetFile]) -> None:
        self._assets = assets

    def assets(self) -> Iterator[AssetFile]:
        return iter(self._assets)

    def close(self) -> None:
        pass


def test_verify_never_follows_paths_out_of_the_library(tmp_path: Path) -> None:
    (tmp_path / "library.db").write_bytes(b"")
    (tmp_path.parent / "outside.jpg").write_bytes(b"x")
    evil = AssetFile(1, "0" * 64, "../outside.jpg", thumb_path="/etc/passwd")
    transfer = LibraryTransfer(
        LocalFileTree(), Blake3Hasher(), lambda a, b: None, lambda _db: ListIndex([evil])
    )
    report = transfer.verify(tmp_path)
    assert report.missing == ["../outside.jpg"] and report.missing_derived == ["/etc/passwd"]
    many = [AssetFile(n, "0" * 64, f"originals/{n}.jpg") for n in range(15)]
    lines = (
        LibraryTransfer(
            LocalFileTree(), Blake3Hasher(), lambda a, b: None, lambda _db: ListIndex(many)
        )
        .verify(tmp_path)
        .lines(show=10)
    )
    assert "      … and 5 more" in lines
