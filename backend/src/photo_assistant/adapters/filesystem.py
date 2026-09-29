"""Hashing, walking source folders (read-only) and the library store on disk."""

import os
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from blake3 import blake3

from photo_assistant.domain.library_paths import ensure_relative
from photo_assistant.domain.model import Source
from photo_assistant.ports import SourceFile

_CHUNK = 1024 * 1024


class Blake3Hasher:
    def hash_file(self, path: Path) -> str:
        digest = blake3()
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
        return digest.hexdigest()


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FolderSourceReader:
    """Walks a source folder. Never follows symlinks out of it, never writes to it."""

    def walk(self, source: Source) -> Iterator[SourceFile]:
        root = Path(source.root)
        if not root.is_dir():
            raise FileNotFoundError(f"source folder not found: {root}")
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                yield SourceFile(
                    relative_path=path.relative_to(root).as_posix(),
                    absolute_path=path,
                    byte_size=stat.st_size,
                    mtime=datetime.fromtimestamp(stat.st_mtime, UTC),
                )


class HashMismatchError(RuntimeError):
    """The copy in the library does not match the source: never keep it."""


class DiskLibraryStore:
    """The data root. Everything the database refers to lives under here."""

    def __init__(self, data_root: Path, hasher: Blake3Hasher | None = None) -> None:
        self.root = data_root
        self._hasher = hasher or Blake3Hasher()
        self._tmp = data_root / "tmp"

    def absolute(self, relative_path: str) -> Path:
        return self.root / ensure_relative(relative_path)

    def store_original(self, source_file: Path, relative_path: str, content_hash: str) -> None:
        target = self.absolute(relative_path)
        if target.exists() and self._hasher.hash_file(target) == content_hash:
            return  # already there from an interrupted earlier run
        target.parent.mkdir(parents=True, exist_ok=True)
        self._tmp.mkdir(parents=True, exist_ok=True)
        partial = self._tmp / f"{uuid.uuid4().hex}.partial"
        try:
            with source_file.open("rb") as src, partial.open("wb") as dst:
                shutil.copyfileobj(src, dst, _CHUNK)
                dst.flush()
                os.fsync(dst.fileno())
            if self._hasher.hash_file(partial) != content_hash:
                raise HashMismatchError(f"copy of {source_file} does not match its hash")
            partial.chmod(0o444)  # originals are read-only in the library too
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)

    def free_bytes(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.root).free
