"""Backups end to end: real importer, real SQLite, real restic, repository in a temp folder."""

import shutil
from pathlib import Path

import pytest
import pyvips  # type: ignore[import-untyped]

from photo_assistant.api.ops_services import build_ops_services
from photo_assistant.api.settings import OpsSettings
from photo_assistant.domain.backup import BackupRunStatus, NewBackupTarget
from tests.conftest import snapshot_tree
from tests.fixtures.expected import IMPORTED
from tests.library_builder import build_library, import_more

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing"),
]


@pytest.fixture
def library(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures" / "photos", source)
    build_library(tmp_path / "data", source)
    return tmp_path / "data"


@pytest.fixture
def password(tmp_path: Path) -> Path:
    path = tmp_path / "home" / ".config" / "photo-assistant" / "restic-password"
    path.parent.mkdir(parents=True)
    path.write_text("a long passphrase kept outside the library\n")
    path.chmod(0o600)
    return path


def _ops(tmp_path: Path, library: Path) -> OpsSettings:
    (tmp_path / "scratch").mkdir(exist_ok=True)
    return OpsSettings(
        restic_cache_dir=tmp_path / "restic-cache",
        backup_scratch_dir=tmp_path / "scratch",
        backup_restore_sample=50,
    )


def _library_files(root: Path) -> dict[str, tuple[str, int, int]]:
    """Everything a backup must never change (the database is allowed to record runs)."""
    return {
        k: v
        for k, v in snapshot_tree(root).items()
        if k.split("/")[0] in {"originals", "derived", "recipes", "config"}
    }


def test_backup_then_restore_test_against_the_database_hashes(
    library: Path, password: Path, tmp_path: Path
) -> None:
    ops = build_ops_services(library, _ops(tmp_path, library))
    try:
        disk = tmp_path / "backup-disk"
        disk.mkdir()
        target = ops.backup.add_target(
            NewBackupTarget("External disk", str(disk / "photos"), str(password))
        )
        first = ops.backup.run_now(target.id)
        assert first.status is BackupRunStatus.SUCCEEDED, first.error
        assert first.repo_bytes and first.bytes_added

        test = ops.backup.restore_test(target.id)
        assert test.status is BackupRunStatus.SUCCEEDED, test.error
        assert f"restored {len(IMPORTED) + 1} photos" in (test.details or "")
        assert "every hash matches" in (test.details or "")

        more = tmp_path / "more"
        more.mkdir()
        pyvips.Image.black(64, 48).add(90).cast("uchar").jpegsave(str(more / "new.jpg"))
        import_more(library, more)
        second = ops.backup.run_now(target.id)
        assert second.status is BackupRunStatus.SUCCEEDED, second.error
        assert (second.bytes_added or 0) < (first.bytes_added or 0), "incremental"

        (status,) = ops.backup.status()
        assert status.last_success_at is not None and not status.needs_attention
        assert status.repo_bytes == second.repo_bytes
    finally:
        ops.close()


def test_failed_backups_leave_the_library_untouched(
    library: Path, password: Path, tmp_path: Path
) -> None:
    before = _library_files(library)
    ops = build_ops_services(library, _ops(tmp_path, library))
    try:
        disk = tmp_path / "disk"
        disk.mkdir()
        good = ops.backup.add_target(NewBackupTarget("Disk", str(disk / "repo"), str(password)))
        assert ops.backup.run_now(good.id).status is BackupRunStatus.SUCCEEDED
        password.write_text("someone changed it\n")
        wrong = ops.backup.run_now(good.id)
        assert wrong.status is BackupRunStatus.FAILED and "wrong password" in (wrong.error or "")
    finally:
        ops.close()
    assert _library_files(library) == before


def test_a_backup_to_a_disk_that_is_not_there_is_skipped_and_creates_nothing(
    library: Path, password: Path, tmp_path: Path
) -> None:
    before = _library_files(library)
    ops = build_ops_services(library, _ops(tmp_path, library))
    try:
        gone = tmp_path / "unplugged"
        target = ops.backup.add_target(
            NewBackupTarget("Unplugged disk", str(gone / "photos"), str(password))
        )
        run = ops.backup.run_now(target.id)
        assert run.status is BackupRunStatus.SKIPPED and "plug it in" in (run.error or "")
        assert not gone.exists(), "no repository is made where the disk should be"
    finally:
        ops.close()
    assert _library_files(library) == before


def test_ops_services_start_and_stop(library: Path, tmp_path: Path) -> None:
    ops = build_ops_services(library, _ops(tmp_path, library))
    ops.start()
    assert ops.periodic.is_running
    ops.close()
    idle = build_ops_services(library, OpsSettings(backup_enabled=False))
    assert idle.periodic.tick() == []
    idle.close()
