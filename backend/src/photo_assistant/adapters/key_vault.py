"""KeyVault in a folder of this machine: one file per backup key, readable by this user only.

restic reads the key from the file (``--password-file``), so the key never appears on a
command line or in the database.
"""

import os
import secrets
from pathlib import Path

from photo_assistant.ports.backup import PasswordFileError


class FileKeyVault:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def create(self) -> tuple[Path, str]:
        self._folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._folder.chmod(0o700)
        key = secrets.token_urlsafe(32)
        key_file = self._folder / f"backup-{secrets.token_hex(8)}.key"
        # O_EXCL: never overwrite a key that protects an existing backup
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(f"{key}\n")
            handle.flush()
            os.fsync(handle.fileno())
        # the folder entry too: a repository is created with this key right after, and a
        # power cut must not leave a backup whose key file is gone
        folder = os.open(self._folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
        return key_file, key

    def read(self, key_file: Path) -> str:
        try:
            key = key_file.read_text().strip()
        except FileNotFoundError as exc:
            raise PasswordFileError(
                f"the key file is gone: {key_file} (the saved recovery key still opens the backup)"
            ) from exc
        except (OSError, UnicodeDecodeError) as exc:  # unreadable, or damaged (not text)
            raise PasswordFileError(f"the key file can't be read: {key_file}") from exc
        if not key:
            raise PasswordFileError(f"the key file is empty: {key_file}")
        return key

    def holds(self, key_file: Path) -> bool:
        folder, target = self._folder.resolve(), key_file.resolve()
        return target != folder and target.is_relative_to(folder)

    def discard(self, key_file: Path) -> None:
        key_file.unlink(missing_ok=True)
