"""LocalBackupPlaces: plugged-in disks, rclone remotes and the facts about one place."""

import os
import stat
from pathlib import Path

import pytest

from photo_assistant.adapters.backup_places import LocalBackupPlaces
from photo_assistant.domain.backup import PlaceFacts


def _rclone(tmp_path: Path, script: str) -> str:
    """A stand-in rclone: a shell script that answers the way the test says."""
    fake = tmp_path / "fake-rclone"
    fake.write_text(f"#!/bin/sh\n{script}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return str(fake)


def _places(tmp_path: Path, mounts: str = "", rclone: str = "/nowhere/rclone") -> LocalBackupPlaces:
    table = tmp_path / "mounts"
    table.write_text(mounts)
    return LocalBackupPlaces(
        rclone_binary=rclone, mounts_file=table, disk_roots=(tmp_path / "media",)
    )


def test_disks_are_the_mounted_folders_under_the_media_roots(tmp_path: Path) -> None:
    usb = tmp_path / "media" / "c" / "My Disk"
    usb.mkdir(parents=True)
    gone = tmp_path / "media" / "c" / "Unplugged"
    spaced = str(usb).replace(" ", "\\040")
    mounts = (
        f"/dev/sda1 / ext4 rw 0 0\n"
        f"/dev/sdb1 {spaced} exfat rw 0 0\n"
        f"/dev/sdc1 {gone} exfat rw 0 0\n"
        f"tmpfs {tmp_path} tmpfs rw 0 0\n"
        "garbage\n"
    )
    (disk,) = _places(tmp_path, mounts).disks()
    assert (disk.path, disk.label) == (str(usb), "My Disk")
    assert disk.free_bytes > 0


def test_no_mount_table_means_no_disks(tmp_path: Path) -> None:
    places = LocalBackupPlaces(mounts_file=tmp_path / "missing", disk_roots=(tmp_path,))
    assert places.disks() == []


def test_remotes_come_from_rclone_and_are_empty_without_it(tmp_path: Path) -> None:
    listed = _rclone(tmp_path, 'echo "proton:"; echo "nas:"; echo')
    assert _places(tmp_path, rclone=listed).remotes() == ["nas", "proton"]
    assert _places(tmp_path).remotes() == [], "rclone not installed"
    assert _places(tmp_path, rclone=_rclone(tmp_path, "exit 3")).remotes() == []


def test_an_existing_empty_folder_on_this_disk_is_writable_and_on_the_same_disk(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    place = tmp_path / "usb"
    place.mkdir()
    facts = _places(tmp_path).facts(str(place / "photo-assistant-backup"), data)
    assert facts.write_error is None and not facts.holds_backup
    assert facts.same_disk, "tmp_path is one file system"
    assert facts.free_bytes is not None and facts.free_bytes > 0
    assert list(place.iterdir()) == [], "the write check leaves nothing behind"


def test_a_missing_folder_is_reported_as_unplugged_not_created(tmp_path: Path) -> None:
    facts = _places(tmp_path).facts(str(tmp_path / "media" / "Gone" / "backup"), tmp_path)
    assert facts.write_error is not None and "does not exist" in facts.write_error
    assert not (tmp_path / "media").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_a_read_only_folder_is_reported(tmp_path: Path) -> None:
    place = tmp_path / "locked"
    place.mkdir()
    place.chmod(0o500)
    try:
        facts = _places(tmp_path).facts(str(place / "backup"), tmp_path)
    finally:
        place.chmod(0o700)
    assert facts.write_error is not None


def test_a_folder_that_already_holds_a_restic_repository_is_recognised(tmp_path: Path) -> None:
    repository = tmp_path / "usb" / "photo-assistant-backup"
    repository.mkdir(parents=True)
    (repository / "config").write_bytes(b"restic")
    assert _places(tmp_path).facts(str(repository), tmp_path).holds_backup


def test_a_file_where_the_backup_folder_should_be_is_a_write_error(tmp_path: Path) -> None:
    (tmp_path / "backup").write_text("in the way")
    facts = _places(tmp_path).facts(str(tmp_path / "backup"), tmp_path)
    assert facts.write_error is not None and "not a folder" in facts.write_error


def test_cloud_free_space_comes_from_rclone_about_when_the_remote_reports_it(
    tmp_path: Path,
) -> None:
    about = _rclone(
        tmp_path,
        """[ "$1 $2 $3" = "about proton: --json" ] && echo '{"free": 12345, "total": 99}'""",
    )
    facts = _places(tmp_path, rclone=about).facts("rclone:proton:photo-assistant-backup", tmp_path)
    assert facts == PlaceFacts(free_bytes=12345)


@pytest.mark.parametrize(
    "script", ["echo '{}'", "echo nonsense", "exit 1", 'echo \'{"free": "lots"}\'']
)
def test_cloud_free_space_is_unknown_when_rclone_cannot_say(tmp_path: Path, script: str) -> None:
    facts = _places(tmp_path, rclone=_rclone(tmp_path, script)).facts("rclone:nas:x", tmp_path)
    assert facts == PlaceFacts(free_bytes=None)
    assert _places(tmp_path).facts("rclone:nas:x", tmp_path) == PlaceFacts(free_bytes=None)
