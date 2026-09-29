"""Shared fixtures.

`source_guard` enforces rule #1 (originals are sacred): any test that imports from a source
folder must leave it byte-identical. Import tests (M1) take this fixture.
"""

import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest


def snapshot_tree(root: Path) -> dict[str, tuple[str, int]]:
    """Map every file under root to (sha256, mtime_ns). Directories are implied by their files."""
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path.relative_to(root))] = (digest, path.stat().st_mtime_ns)
    return result


@pytest.fixture
def source_guard(tmp_path: Path) -> Iterator[Path]:
    """A source folder that must be unchanged when the test finishes."""
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parent / "fixtures" / "photos", source)
    before = snapshot_tree(source)
    yield source
    after = snapshot_tree(source)
    assert after == before, "a source folder was modified — originals are sacred"
