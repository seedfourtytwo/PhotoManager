from pathlib import Path

import pytest

from tests.conftest import snapshot_tree


def test_snapshot_detects_content_change(tmp_path: Path) -> None:
    photo = tmp_path / "a.jpg"
    photo.write_bytes(b"one")
    before = snapshot_tree(tmp_path)
    photo.write_bytes(b"two")
    assert snapshot_tree(tmp_path) != before


def test_snapshot_detects_deletion_and_addition(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"x")
    before = snapshot_tree(tmp_path)
    (tmp_path / "a.jpg").unlink()
    (tmp_path / "b.jpg").write_bytes(b"x")
    assert snapshot_tree(tmp_path) != before


def test_guard_passes_when_source_is_only_read(source_guard: Path) -> None:
    for f in source_guard.iterdir():
        f.read_bytes()


@pytest.mark.parametrize("name", ["new.jpg"])
def test_guard_sees_the_fixture_folder(source_guard: Path, name: str) -> None:
    assert source_guard.is_dir()
    assert not (source_guard / name).exists()
