"""Backups to an rclone remote use the rclone this app is configured with (binary and config
file), not whatever ``rclone`` and default config restic would pick on its own."""

import shutil
import stat
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.api.ops_services import RcloneTool, build_ops_services
from photo_assistant.api.settings import OpsSettings
from photo_assistant.domain.backup import BackupRunStatus, NewBackupTarget

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing"),
    pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone missing"),
]


def test_restic_is_given_the_apps_own_rclone_binary_and_config(tmp_path: Path) -> None:
    library = tmp_path / "data"
    (library / "originals").mkdir(parents=True)
    (library / "originals" / "a.jpg").write_bytes(b"a photo")
    password = tmp_path / "keys" / "restic-password"
    password.parent.mkdir()
    password.write_text("a long passphrase kept outside the library\n")
    config = tmp_path / "our rclone.conf"  # a remote only this file knows
    config.write_text("[patest]\ntype = local\n")
    used = tmp_path / "our-rclone-was-used"
    binary = tmp_path / "our rclone"
    binary.write_text(f'#!/bin/sh\ntouch "{used}"\nexec "{shutil.which("rclone")}" "$@"\n')
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "scratch").mkdir()
    settings = OpsSettings(
        restic_cache_dir=tmp_path / "restic-cache",
        backup_scratch_dir=tmp_path / "scratch",
        backup_key_dir=tmp_path / "keys",
    )
    db = Database.open(library / "library.db")
    ops = build_ops_services(
        library,
        settings,
        db=db,
        rclone=RcloneTool(str(binary), config),
        queue=SqliteRepository(db),
    )
    try:
        target = ops.backup.add_target(
            NewBackupTarget("Server", f"rclone:patest:{tmp_path / 'remote-repo'}", str(password))
        )
        run = ops.backup.run_now(target.id)
        assert run.status is BackupRunStatus.SUCCEEDED, run.error
        assert (tmp_path / "remote-repo" / "config").is_file()
        assert used.exists(), "restic started plain 'rclone' instead of the configured one"
    finally:
        ops.close()
