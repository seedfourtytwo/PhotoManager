"""Test mode only: a copy of the library's files beside the database snapshots, so the E2E
reset (``POST /__test/reset``) puts back what a test deleted (emptying the trash removes
originals and derivatives) and removes what a test added. ``scripts/e2e_seed.py`` saves it;
only a throw-away E2E data root ever has one.
"""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

LIBRARY_FOLDERS = ("originals", "derived")  # what the library itself writes and removes


def save_library_files(data_root: Path, snapshot: Path) -> None:
    snapshot.mkdir(parents=True, exist_ok=True)  # an empty library has a snapshot too
    for folder in LIBRARY_FOLDERS:
        if (data_root / folder).is_dir():
            shutil.copytree(data_root / folder, snapshot / folder, dirs_exist_ok=True)


def restore_library_files(snapshot: Path, data_root: Path) -> None:
    """Make ``originals/`` and ``derived/`` match the snapshot, copying only what changed."""
    wanted = set(_files(snapshot))
    for relative in set(_files(data_root)) - wanted:
        (data_root / relative).unlink()
    for relative in wanted:
        source, target = snapshot / relative, data_root / relative
        if not _same(source, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)  # originals are read-only
            shutil.copy2(source, target)


def _files(root: Path) -> Iterator[str]:
    for folder in LIBRARY_FOLDERS:
        for dirpath, _, filenames in os.walk(root / folder):
            for name in filenames:
                yield (Path(dirpath) / name).relative_to(root).as_posix()


def _same(source: Path, target: Path) -> bool:
    if not target.is_file():
        return False
    a, b = source.stat(), target.stat()
    return (a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns)
