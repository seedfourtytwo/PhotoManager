"""StagingFolders: deletes a removed cloud source's pulled copy, and nothing else."""

from pathlib import Path

from photo_assistant.adapters.staging_folders import StagingFolders


def _staging(tmp_path: Path) -> Path:
    root = tmp_path / "data" / "staging"
    for source_id in (3, 4):
        (root / str(source_id) / "2024").mkdir(parents=True)
        (root / str(source_id) / "2024" / "a.jpg").write_bytes(b"x")
    return root


def test_removes_that_sources_copy_and_leaves_the_others(tmp_path: Path) -> None:
    root = _staging(tmp_path)
    StagingFolders(root).remove(3)
    assert not (root / "3").exists()
    assert (root / "4" / "2024" / "a.jpg").read_bytes() == b"x"


def test_a_source_that_was_never_pulled_has_nothing_to_remove(tmp_path: Path) -> None:
    root = _staging(tmp_path)
    StagingFolders(root).remove(9)
    assert sorted(p.name for p in root.iterdir()) == ["3", "4"]


def test_a_staging_entry_that_is_a_link_is_unlinked_never_followed(tmp_path: Path) -> None:
    root = _staging(tmp_path)
    elsewhere = tmp_path / "Pictures"
    elsewhere.mkdir()
    (elsewhere / "keep.jpg").write_bytes(b"k")
    (root / "7").symlink_to(elsewhere, target_is_directory=True)
    StagingFolders(root).remove(7)
    assert not (root / "7").exists()
    assert (elsewhere / "keep.jpg").read_bytes() == b"k"
