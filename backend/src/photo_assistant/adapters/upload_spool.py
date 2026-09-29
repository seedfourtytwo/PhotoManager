"""Receive uploads into ``data/tmp`` (hashing as bytes arrive), then move them atomically.

Temp files use the ``.partial`` suffix so ``DiskLibraryStore.sweep_tmp`` clears leftovers from a
crash. ``commit`` hard-links into place (fails if the name exists, so nothing is ever
overwritten) and then drops the temp name; ``data/tmp`` and ``data/inbox`` share a filesystem.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from blake3 import blake3

from photo_assistant.domain.uploads import HEAD_BYTES
from photo_assistant.ports.upload import SpooledUpload, UploadTooLargeError

_MAX_NAME_TRIES = 10_000


class _DiskWriter:
    def __init__(self, path: Path, max_bytes: int) -> None:
        self._path = path
        self._max = max_bytes
        self._size = 0
        self._head = b""
        self._digest = blake3()
        self._file: BinaryIO | None = path.open("xb")

    def write(self, chunk: bytes) -> None:
        if self._file is None:
            raise ValueError("this upload was already finished or discarded")
        if self._size + len(chunk) > self._max:
            self.discard()
            raise UploadTooLargeError(f"larger than the {self._max} byte upload limit")
        self._file.write(chunk)
        self._digest.update(chunk)
        if len(self._head) < HEAD_BYTES:
            self._head = (self._head + chunk)[:HEAD_BYTES]
        self._size += len(chunk)

    def finish(self) -> SpooledUpload:
        if self._file is None:
            raise ValueError("this upload was already finished or discarded")
        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()
        self._file = None
        return SpooledUpload(self._path, self._digest.hexdigest(), self._size, self._head)

    def discard(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self._path.unlink(missing_ok=True)


def _single_component(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


class DiskUploadSpool:
    def __init__(self, tmp_dir: Path) -> None:
        self._tmp = tmp_dir

    def open(self, max_bytes: int) -> _DiskWriter:
        self._tmp.mkdir(parents=True, exist_ok=True)
        return _DiskWriter(self._tmp / f"upload-{uuid.uuid4().hex}.partial", max_bytes)

    def commit(self, upload: SpooledUpload, folder: Path, names: Iterator[str]) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        for _, name in zip(range(_MAX_NAME_TRIES), names, strict=False):
            if not _single_component(name):
                raise ValueError(f"refusing unsafe file name {name!r}")
            target = folder / name
            try:
                os.link(upload.path, target)
            except FileExistsError:
                continue
            upload.path.unlink()
            return target
        raise FileExistsError(f"no free file name in {folder}")

    def discard(self, upload: SpooledUpload) -> None:
        upload.path.unlink(missing_ok=True)
