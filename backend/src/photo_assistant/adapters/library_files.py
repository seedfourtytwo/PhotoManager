"""FileTree and LibraryIndex on the local disk, for export-library and verify-library."""

import os
import shutil
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path

from photo_assistant.adapters.filesystem import Blake3Hasher
from photo_assistant.adapters.sqlite_snapshot import open_read_only
from photo_assistant.ports.backup import AssetFile
from photo_assistant.ports.library_files import (
    CopyOutcome,
    CopyResult,
    CopyVerificationError,
    LibraryUnreadableError,
)

_CHUNK = 1024 * 1024


class LocalFileTree:
    def __init__(self, hasher: Blake3Hasher | None = None) -> None:
        self._hasher = hasher or Blake3Hasher()

    def files_under(self, root: Path, folder: str) -> Iterator[str]:
        base = root / folder
        if not base.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if name.endswith(".partial") or path.is_symlink() or not path.is_file():
                    continue
                yield path.relative_to(root).as_posix()

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def _same(self, source: Path, destination: Path, size: int) -> bool:
        if not destination.is_file() or destination.stat().st_size != size:
            return False
        return self._hasher.hash_file(destination) == self._hasher.hash_file(source)

    def copy_verified(self, source: Path, destination: Path) -> CopyResult:
        size = source.stat().st_size
        if self._same(source, destination, size):
            return CopyResult(CopyOutcome.ALREADY_THERE, 0)
        expected = self._hasher.hash_file(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{uuid.uuid4().hex}.partial")
        try:
            with source.open("rb") as src, partial.open("wb") as dst:
                shutil.copyfileobj(src, dst, _CHUNK)
                dst.flush()
                os.fsync(dst.fileno())
            if self._hasher.hash_file(partial) != expected:
                raise CopyVerificationError(f"copy of {source} does not match the original")
            shutil.copystat(source, partial)  # read-only originals stay read-only
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        return CopyResult(CopyOutcome.COPIED, size)


class SqliteLibraryIndex:
    def __init__(self, database: Path) -> None:
        try:
            self._conn = open_read_only(database)
        except (OSError, sqlite3.Error) as exc:
            raise LibraryUnreadableError(f"no readable library database at {database}") from exc

    def assets(self) -> Iterator[AssetFile]:
        try:
            rows = self._conn.execute(
                """SELECT id, content_hash, library_path, thumb_path, preview_path
                   FROM asset ORDER BY id"""
            )
            for r in rows:
                yield AssetFile(
                    r["id"],
                    r["content_hash"],
                    r["library_path"],
                    r["thumb_path"],
                    r["preview_path"],
                )
        except sqlite3.DatabaseError as exc:
            raise LibraryUnreadableError(f"cannot read the library database: {exc}") from exc

    def close(self) -> None:
        self._conn.close()
