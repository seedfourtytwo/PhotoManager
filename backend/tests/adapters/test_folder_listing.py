"""LocalFolders: the sub-folders of one folder, for picking a folder in the web app."""

import os
from pathlib import Path

import pytest

from photo_assistant.adapters.folder_listing import FolderUnavailableError, LocalFolders


def test_lists_sub_folders_by_name_without_files_or_hidden_ones(tmp_path: Path) -> None:
    for name in ("zebra", "Alps 2019", "beach", ".cache"):
        (tmp_path / name).mkdir()
    (tmp_path / "notes.txt").write_text("a file")
    listing = LocalFolders().list(tmp_path)
    assert listing.path == str(tmp_path) and listing.parent == str(tmp_path.parent)
    assert [f.name for f in listing.folders] == ["Alps 2019", "beach", "zebra"]
    assert listing.folders[0].path == str(tmp_path / "Alps 2019")
    assert not listing.truncated


def test_the_top_of_the_disk_has_no_parent() -> None:
    assert LocalFolders().list(Path("/")).parent is None


def test_a_link_to_a_folder_is_listed_and_opens_the_real_folder(tmp_path: Path) -> None:
    real = tmp_path / "disk" / "Pictures"
    real.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    (home / "Pictures").symlink_to(real)
    (home / "broken").symlink_to(tmp_path / "nowhere")
    assert [f.name for f in LocalFolders().list(home).folders] == ["Pictures"]
    assert LocalFolders().list(home / "Pictures").path == str(real)


def test_folder_names_with_control_characters_are_left_out(tmp_path: Path) -> None:
    (tmp_path / "ok").mkdir()
    (tmp_path / "bad\nname").mkdir()
    assert [f.name for f in LocalFolders().list(tmp_path).folders] == ["ok"]


def test_a_huge_folder_is_cut_off_and_says_so(tmp_path: Path) -> None:
    for n in range(7):
        (tmp_path / f"f{n}").mkdir()
    listing = LocalFolders(limit=5).list(tmp_path)
    assert [f.name for f in listing.folders] == ["f0", "f1", "f2", "f3", "f4"]
    assert listing.truncated


def test_a_missing_folder_a_file_and_an_unreadable_folder_say_why(tmp_path: Path) -> None:
    with pytest.raises(FolderUnavailableError, match="not found"):
        LocalFolders().list(tmp_path / "nope")
    a_file = tmp_path / "photo.jpg"
    a_file.write_text("x")
    with pytest.raises(FolderUnavailableError, match="not a folder"):
        LocalFolders().list(a_file)
    if os.geteuid() != 0:
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(0o000)
        try:
            with pytest.raises(FolderUnavailableError, match="can't be read"):
                LocalFolders().list(locked)
        finally:
            locked.chmod(0o700)


def test_a_missing_folder_is_told_apart_from_an_unreadable_one(tmp_path: Path) -> None:
    from photo_assistant.adapters.folder_listing import FolderMissingError

    with pytest.raises(FolderMissingError):
        LocalFolders().list(tmp_path / "nope")


def test_create_makes_one_folder_and_explains_refusals(tmp_path: Path) -> None:
    folders = LocalFolders()
    assert folders.create(tmp_path / "new") == tmp_path / "new"
    assert (tmp_path / "new").is_dir()
    with pytest.raises(FolderUnavailableError, match="already exists"):
        folders.create(tmp_path / "new")
    with pytest.raises(FolderUnavailableError, match="does not exist"):
        folders.create(tmp_path / "a" / "b")
    (tmp_path / "file").write_text("x")
    with pytest.raises(FolderUnavailableError, match="does not exist"):
        folders.create(tmp_path / "file" / "b")
    assert not (tmp_path / "a").exists()
