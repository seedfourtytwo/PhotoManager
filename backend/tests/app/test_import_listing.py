"""Listing a source folder while it changes or refuses: the walk itself, and what the import
makes of a listing that could not be finished."""

import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from photo_assistant.adapters.filesystem import FolderSourceReader
from photo_assistant.app.import_source import SourceUnavailableError
from photo_assistant.domain.model import RunStatus, Source
from photo_assistant.ports import SourceFile
from tests.app.test_import_failures import build


def _listed(root: Path) -> list[str]:
    return [f.relative_path for f in FolderSourceReader().walk(Source(1, "s", str(root)))]


# --- the walk -------------------------------------------------------------------------------------


def test_a_file_that_vanishes_after_a_first_look_does_not_stop_the_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "moving.jpg").write_bytes(b"m")
    real = Path.is_file

    def is_file_then_gone(self: Path) -> bool:
        found = real(self)
        if self.name == "moving.jpg":
            self.unlink(missing_ok=True)  # e.g. a camera app renaming its temporary file
        return found

    monkeypatch.setattr(Path, "is_file", is_file_then_gone)
    assert "a.jpg" in _listed(tmp_path)


def test_a_file_gone_before_it_is_looked_at_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    real = os.walk

    def walk_with_a_ghost(*args: Any, **kwargs: Any) -> Iterator[object]:
        for dirpath, dirnames, filenames in real(*args, **kwargs):
            yield dirpath, dirnames, [*filenames, "ghost.jpg"]

    monkeypatch.setattr(os, "walk", walk_with_a_ghost)
    assert _listed(tmp_path) == ["a.jpg"]


def test_things_that_are_not_plain_files_are_left_out(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    os.mkfifo(tmp_path / "pipe.jpg")
    (tmp_path / "link.jpg").symlink_to(tmp_path / "a.jpg")
    assert _listed(tmp_path) == ["a.jpg"]


def test_a_sub_folder_that_cannot_be_read_is_said_in_the_log_not_passed_over_in_silence(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "hidden.jpg").write_bytes(b"h")
    locked.chmod(0o000)
    try:
        with caplog.at_level(logging.WARNING):
            assert _listed(tmp_path) == ["a.jpg"]
    finally:
        locked.chmod(0o755)
    (record,) = [r for r in caplog.records if "could not be read" in r.getMessage()]
    assert record.__dict__["folder"] == str(locked)
    assert "Permission denied" in record.__dict__["error"]


def test_a_source_folder_that_cannot_be_read_at_all_is_an_error_not_an_empty_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.jpg").write_bytes(b"a")
    root.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            _listed(root)
    finally:
        root.chmod(0o755)


def test_each_file_is_looked_at_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for n in range(5):
        (tmp_path / f"{n}.jpg").write_bytes(b"x")
    looks: list[str] = []
    real_stat, real_lstat = os.stat, os.lstat

    def stat(path: object, *args: object, **kwargs: object) -> os.stat_result:
        looks.append(str(path))
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    def lstat(path: object, *args: object, **kwargs: object) -> os.stat_result:
        looks.append(str(path))
        return real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(os, "lstat", lstat)
    assert len(_listed(tmp_path)) == 5
    assert len([look for look in looks if look.endswith(".jpg")]) == 5


# --- the import -----------------------------------------------------------------------------------


class RefusingReader:
    def __init__(self, error: OSError) -> None:
        self._error = error

    def walk(self, source: Source) -> Iterator[SourceFile]:
        raise self._error
        yield  # pragma: no cover  (makes this a generator, like the real walk)


@pytest.mark.parametrize(
    "error",
    [PermissionError(13, "Permission denied"), FileNotFoundError(2, "No such file or directory")],
)
def test_a_listing_that_fails_in_a_folder_that_is_there_is_recorded_with_the_real_reason(
    tmp_path: Path, error: OSError
) -> None:
    repo, importer, folder = build(tmp_path, reader=RefusingReader(error))
    source = repo.add_source("Pics", str(folder))
    with pytest.raises(SourceUnavailableError, match=error.strerror or ""):
        importer.run(source.id)
    (run,) = repo.list_import_runs(source.id)
    assert run["status"] == RunStatus.FAILED.value
    assert error.strerror in str(run["message"])  # type: ignore[operator]
    assert "folder not found" not in str(run["message"])
