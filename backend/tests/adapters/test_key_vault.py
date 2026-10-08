"""FileKeyVault: backup keys the app makes, kept in files only this user can read."""

import stat
from pathlib import Path

import pytest

from photo_assistant.adapters.key_vault import FileKeyVault
from photo_assistant.ports.backup import PasswordFileError


def test_a_new_key_is_long_random_and_private_to_this_user(tmp_path: Path) -> None:
    vault = FileKeyVault(tmp_path / "keys" / "backup")
    first_file, first = vault.create()
    second_file, second = vault.create()
    assert first != second and first_file != second_file
    assert len(first) >= 40 and first.isascii() and first == first.strip()
    assert stat.S_IMODE(first_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(first_file.parent.stat().st_mode) == 0o700
    assert vault.read(first_file) == first
    assert first_file.read_text() == f"{first}\n", "restic reads the first line"


def test_reading_a_missing_empty_or_unreadable_key_says_so(tmp_path: Path) -> None:
    vault = FileKeyVault(tmp_path)
    with pytest.raises(PasswordFileError, match="is gone"):
        vault.read(tmp_path / "nope.key")
    empty = tmp_path / "empty.key"
    empty.write_text("\n")
    with pytest.raises(PasswordFileError, match="is empty"):
        vault.read(empty)
    with pytest.raises(PasswordFileError):
        vault.read(tmp_path)  # a folder


def test_discard_removes_the_file_and_is_quiet_when_it_is_gone(tmp_path: Path) -> None:
    vault = FileKeyVault(tmp_path)
    key_file, _ = vault.create()
    vault.discard(key_file)
    vault.discard(key_file)
    assert not key_file.exists()
