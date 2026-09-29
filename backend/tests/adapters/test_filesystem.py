from datetime import UTC, datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import (
    Blake3Hasher,
    DiskLibraryStore,
    FolderSourceReader,
    HashMismatchError,
    SystemClock,
)
from photo_assistant.domain.library_paths import InvalidLibraryPathError
from photo_assistant.domain.model import Source
from tests.fixtures.expected import TOTAL_FILES


def test_blake3_known_vector(tmp_path: Path) -> None:
    empty = tmp_path / "e"
    empty.write_bytes(b"")
    assert (
        Blake3Hasher().hash_file(empty)
        == "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    )


def test_walk_lists_every_file_with_relative_posix_paths(source_guard: Path) -> None:
    files = list(FolderSourceReader().walk(Source(1, "fixtures", str(source_guard))))
    assert len(files) == TOTAL_FILES
    paths = [f.relative_path for f in files]
    assert "nested/deeper/IMG_1001 (Copy).JPG" in paths
    assert len(paths) == len(set(paths))
    assert paths == [
        f.relative_path for f in FolderSourceReader().walk(Source(1, "f", str(source_guard)))
    ], "stable order"
    assert all(f.mtime.tzinfo is UTC for f in files)


def test_walk_does_not_follow_symlinks_out_of_the_source(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.jpg").write_bytes(b"x")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "file-link.jpg").symlink_to(outside / "secret.jpg")
    assert list(FolderSourceReader().walk(Source(1, "r", str(root)))) == []


def test_walk_of_missing_folder_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        list(FolderSourceReader().walk(Source(1, "gone", str(tmp_path / "nope"))))


def test_store_copies_verifies_and_makes_read_only(tmp_path: Path) -> None:
    source = tmp_path / "a.jpg"
    source.write_bytes(b"photo bytes")
    digest = Blake3Hasher().hash_file(source)
    store = DiskLibraryStore(tmp_path / "data")
    store.store_original(source, f"originals/2020/01/{digest}.jpg", digest)
    target = store.absolute(f"originals/2020/01/{digest}.jpg")
    assert target.read_bytes() == b"photo bytes"
    assert source.exists(), "never move a source file"
    assert not (target.stat().st_mode & 0o222), "library originals are read-only"
    store.store_original(source, f"originals/2020/01/{digest}.jpg", digest)  # idempotent
    assert list((tmp_path / "data" / "tmp").iterdir()) == []


def test_store_refuses_a_copy_that_does_not_match(tmp_path: Path) -> None:
    source = tmp_path / "a.jpg"
    source.write_bytes(b"photo bytes")
    store = DiskLibraryStore(tmp_path / "data")
    with pytest.raises(HashMismatchError):
        store.store_original(source, "originals/2020/01/x.jpg", "0" * 64)
    assert not store.absolute("originals/2020/01/x.jpg").exists()
    assert list((tmp_path / "data" / "tmp").iterdir()) == []


def test_store_never_resolves_paths_outside_the_root(tmp_path: Path) -> None:
    with pytest.raises(InvalidLibraryPathError):
        DiskLibraryStore(tmp_path).absolute("../escape.jpg")


def test_free_bytes_and_clock(tmp_path: Path) -> None:
    assert DiskLibraryStore(tmp_path / "d").free_bytes() > 0
    assert SystemClock().now().tzinfo is UTC
    assert SystemClock().now() > datetime(2026, 1, 1, tzinfo=UTC)
