"""Ports for moving and verifying a whole library (ARCHITECTURE §6, deployment path)."""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from photo_assistant.ports.backup import AssetFile


class CopyVerificationError(RuntimeError):
    """The copy's bytes differ from the source: it was not kept."""


class LibraryUnreadableError(RuntimeError):
    """There is no library at that place, or its database cannot be read."""


class CopyOutcome(StrEnum):
    COPIED = "copied"
    ALREADY_THERE = "already_there"  # an earlier, interrupted run copied it: resumable


@dataclass(frozen=True, slots=True)
class CopyResult:
    outcome: CopyOutcome
    byte_size: int


class FileTree(Protocol):
    def files_under(self, root: Path, folder: str) -> Iterator[str]:
        """Regular files under ``root/folder`` as posix paths relative to ``root``.

        Never follows symlinks; skips half-written ``*.partial`` files. Nothing if absent."""
        ...

    def copy_verified(self, source: Path, destination: Path) -> CopyResult:
        """Copy (never move), verify by hash, keep permissions and mtime, atomic rename.

        A destination that already has the same bytes is left alone."""
        ...

    def is_file(self, path: Path) -> bool: ...


class LibraryIndex(Protocol):
    """Read-only view of a library database: which files each asset owns."""

    def assets(self) -> Iterator[AssetFile]: ...

    def close(self) -> None: ...
