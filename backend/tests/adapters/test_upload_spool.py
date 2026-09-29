from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore
from photo_assistant.adapters.upload_spool import DiskUploadSpool
from photo_assistant.domain.uploads import numbered_names
from photo_assistant.ports.upload import UploadTooLargeError


def test_an_upload_is_hashed_while_it_streams_in(tmp_path: Path) -> None:
    spool = DiskUploadSpool(tmp_path / "tmp")
    writer = spool.open(max_bytes=100)
    for chunk in (b"\xff\xd8\xff", b"hello", b" world"):
        writer.write(chunk)
    upload = writer.finish()
    assert upload.path.parent == tmp_path / "tmp"
    assert upload.path.read_bytes() == b"\xff\xd8\xffhello world"
    assert upload.content_hash == Blake3Hasher().hash_file(upload.path)
    assert (upload.byte_size, upload.head[:3]) == (14, b"\xff\xd8\xff")


def test_going_over_the_limit_stops_and_removes_the_partial_file(tmp_path: Path) -> None:
    spool = DiskUploadSpool(tmp_path / "tmp")
    writer = spool.open(max_bytes=10)
    writer.write(b"x" * 10)
    with pytest.raises(UploadTooLargeError):
        writer.write(b"y")
    assert list((tmp_path / "tmp").iterdir()) == []
    writer.discard()  # harmless afterwards


def test_commit_never_overwrites_and_picks_the_next_free_name(tmp_path: Path) -> None:
    spool = DiskUploadSpool(tmp_path / "tmp")
    inbox = tmp_path / "inbox" / "1"
    stored = []
    for content in (b"one", b"two"):
        writer = spool.open(100)
        writer.write(content)
        stored.append(spool.commit(writer.finish(), inbox, numbered_names("a.jpg")))
    assert [p.name for p in stored] == ["a.jpg", "a (2).jpg"]
    assert (inbox / "a.jpg").read_bytes() == b"one"
    assert list((tmp_path / "tmp").iterdir()) == []


def test_commit_refuses_names_that_are_not_a_single_component(tmp_path: Path) -> None:
    spool = DiskUploadSpool(tmp_path / "tmp")
    writer = spool.open(100)
    writer.write(b"x")
    upload = writer.finish()
    for bad in ("../x.jpg", "a/b.jpg", "..", ""):
        with pytest.raises(ValueError, match="file name"):
            spool.commit(upload, tmp_path / "inbox", iter([bad]))
    spool.discard(upload)
    assert not upload.path.exists()


def test_an_abandoned_upload_is_discarded(tmp_path: Path) -> None:
    spool = DiskUploadSpool(tmp_path / "tmp")
    writer = spool.open(100)
    writer.write(b"half")
    writer.discard()
    assert list((tmp_path / "tmp").iterdir()) == []


def test_leftovers_from_a_crash_are_swept_by_the_library_store(tmp_path: Path) -> None:
    spool = DiskUploadSpool(tmp_path / "data" / "tmp")
    writer = spool.open(100)
    writer.write(b"received, but the server stopped before moving it")
    writer.finish()
    assert DiskLibraryStore(tmp_path / "data").sweep_tmp() == 1
