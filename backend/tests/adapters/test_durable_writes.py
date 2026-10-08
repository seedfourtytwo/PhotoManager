"""Small files that must survive a power cut are flushed to the disk before they count: a new
backup key (a repository is created with it right after) and Proton's list of fetched photos."""

import os
from pathlib import Path

import pytest

from photo_assistant.adapters.key_vault import FileKeyVault
from photo_assistant.ports.backup import PasswordFileError
from tests.proton_cloud import Cloud


@pytest.fixture
def synced(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The path of everything handed to os.fsync during the test."""
    real, seen = os.fsync, []

    def fsync(fd: int) -> None:
        seen.append(str(Path(f"/proc/self/fd/{fd}").readlink()))
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return seen


def test_a_new_backup_key_is_on_the_disk_before_it_is_used(
    tmp_path: Path, synced: list[str]
) -> None:
    key_file, _ = FileKeyVault(tmp_path / "keys").create()
    assert synced == [str(key_file), str(key_file.parent)], "the file, then its folder entry"


def test_protons_list_of_fetched_photos_is_on_the_disk_before_it_replaces_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synced: list[str]
) -> None:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.photo("p1", "a.jpg")
    cloud.pull()
    assert synced == [str(cloud.staging.parent / "7.proton.json.new")]


def test_a_key_file_that_is_not_text_is_a_plain_error(tmp_path: Path) -> None:
    damaged = tmp_path / "backup.key"
    damaged.write_bytes(b"\xff\xfe\x00 not text")
    with pytest.raises(PasswordFileError, match="can't be read"):
        FileKeyVault(tmp_path).read(damaged)
