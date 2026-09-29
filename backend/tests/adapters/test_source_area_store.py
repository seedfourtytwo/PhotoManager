from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.adapters.source_area_store import SourceAreaStore
from photo_assistant.ports import ImportBusyError


@pytest.fixture
def data(tmp_path: Path) -> Path:
    return tmp_path / "data"


def test_folders_inside_staging_and_inbox_may_be_sources(data: Path) -> None:
    store = SourceAreaStore(DiskLibraryStore(data), [data / "staging", data / "inbox"])
    assert not store.overlaps(data / "staging" / "1")
    assert not store.overlaps(data / "inbox" / "7")


@pytest.mark.parametrize(
    "folder", ["", "staging", "inbox", "originals", "originals/2020", "staging/../originals"]
)
def test_everything_else_in_the_library_is_still_refused(data: Path, folder: str) -> None:
    store = SourceAreaStore(DiskLibraryStore(data), [data / "staging", data / "inbox"])
    assert store.overlaps(data / folder)


def test_folders_containing_the_library_are_refused(data: Path) -> None:
    store = SourceAreaStore(DiskLibraryStore(data), [data / "staging"])
    assert store.overlaps(data.parent)
    assert not store.overlaps(data.parent / "elsewhere")


def test_everything_else_is_delegated(data: Path, tmp_path: Path) -> None:
    inner = DiskLibraryStore(data)
    store = SourceAreaStore(inner, [data / "staging"])
    assert store.absolute("originals/x.jpg") == inner.absolute("originals/x.jpg")
    assert store.free_bytes() > 0
    photo = tmp_path / "a.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    from photo_assistant.adapters.filesystem import Blake3Hasher

    digest = Blake3Hasher().hash_file(photo)
    store.store_original(photo, "originals/a.jpg", digest)
    assert (data / "originals" / "a.jpg").read_bytes() == b"\xff\xd8\xff"
    with store.exclusive_import(), pytest.raises(ImportBusyError), inner.exclusive_import():
        pass
