"""Every external tool is started so that it can neither wait for a keyboard nor hang for good:
no inherited stdin, always a timeout, and the timeout fits the command."""

import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from photo_assistant.adapters.exiftool_reader import ExifToolStripper
from photo_assistant.adapters.rclone_sync import RcloneSync
from photo_assistant.adapters.restic_backup import ResticBackup
from photo_assistant.domain.backup import Retention
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.backup import BackupError, RepositoryRef
from photo_assistant.ports.sync import SyncOptions
from tests.proton_cloud import Cloud

Call = tuple[list[str], dict[str, Any]]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    """Every subprocess.run of the test: its arguments and keyword options."""
    real, seen = subprocess.run, []

    def run(args: list[str], **kwargs: Any) -> Any:
        seen.append((list(args), kwargs))
        return real(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    return seen


def _script(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _no_keyboard(calls: list[Call]) -> bool:
    return bool(calls) and all(kw.get("stdin") is subprocess.DEVNULL for _, kw in calls)


# --- rclone ---------------------------------------------------------------------------------------


def test_rclone_can_never_wait_for_a_password_at_a_keyboard(
    tmp_path: Path, calls: list[Call]
) -> None:
    sync = RcloneSync(binary=_script(tmp_path, "rclone", "exit 0"))
    sync.pull(RemoteConfig("mega", "Photos"), tmp_path / "staging", SyncOptions())
    sync.list_remotes()
    assert len(calls) == 2 and _no_keyboard(calls)
    assert all("--ask-password=false" in args for args, _ in calls)


# --- Proton Drive ---------------------------------------------------------------------------------


def test_proton_questions_asked_from_a_web_request_give_up_after_half_a_minute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: list[Call]
) -> None:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.folder("/", {"type": "folder", "uid": "m", "name": "my-files"})
    cloud.folder("/my-files", {"type": "folder", "uid": "a", "name": "Trips"})
    cloud.drive.check()
    cloud.drive.folders("/my-files")
    assert [kw["timeout"] for _, kw in calls] == [30.0, 30.0]
    cloud.pull(RemoteConfig.proton("/my-files"))  # a long job: a big Drive may take minutes
    assert calls[2][1]["timeout"] == 600.0
    assert _no_keyboard(calls)


# --- restic ---------------------------------------------------------------------------------------

_FAKE_RESTIC = """
case " $* " in
  *" snapshots "*) echo '[]' ;;
  *" stats "*) echo '{"total_size": 1}' ;;
  *" backup "*) echo '{"message_type": "summary", "snapshot_id": "abc"}' ;;
esac
"""
_VERBS = ("cat", "init", "snapshots", "backup", "unlock", "forget", "check", "restore", "stats")


def _verb(args: list[str]) -> str:
    return next(a for a in args if a in _VERBS)


def test_restic_metadata_commands_get_a_short_timeout_and_the_heavy_ones_a_long_one(
    tmp_path: Path, calls: list[Call]
) -> None:
    engine = ResticBackup(
        binary=_script(tmp_path, "restic", _FAKE_RESTIC), quick_timeout=5, long_timeout=50
    )
    repo = RepositoryRef(str(tmp_path / "repo"), tmp_path / "password")
    (tmp_path / "data" / "originals").mkdir(parents=True)
    engine.ensure_repository(repo)
    engine.backup(repo, tmp_path / "data", ["originals"])
    engine.forget(repo, Retention(7, 4, 12))
    engine.check(repo)
    engine.restore(repo, "abc", ["originals/a.jpg"], tmp_path / "restored")
    engine.repository_size(repo)
    timeouts = {_verb(args): kw.get("timeout") for args, kw in calls}
    assert timeouts == {
        "cat": 5,
        "snapshots": 5,
        "unlock": 5,
        "stats": 5,
        "backup": 50,
        "forget": 50,
        "check": 50,
        "restore": 50,
    }
    assert _no_keyboard(calls)


def test_a_new_repository_is_created_with_the_long_timeout(
    tmp_path: Path, calls: list[Call]
) -> None:
    fake = _script(tmp_path, "restic", 'case " $* " in *" cat "*) exit 10 ;; esac')
    engine = ResticBackup(binary=fake, quick_timeout=5, long_timeout=50)
    assert engine.ensure_repository(RepositoryRef(str(tmp_path / "repo"), tmp_path / "pw"))
    assert [(_verb(args), kw.get("timeout")) for args, kw in calls] == [("cat", 5), ("init", 50)]


def test_a_restic_that_hangs_is_stopped_and_says_so(tmp_path: Path) -> None:
    engine = ResticBackup(binary=_script(tmp_path, "restic", "sleep 30"), quick_timeout=0.2)
    repo = RepositoryRef(str(tmp_path / "repo"), tmp_path / "password")
    with pytest.raises(BackupError, match="did not answer"):
        engine.latest_snapshot(repo)


# --- exiftool -------------------------------------------------------------------------------------


def test_stripping_metadata_cannot_hang_a_download(tmp_path: Path, calls: list[Call]) -> None:
    photo = tmp_path / "copy.jpg"
    photo.write_bytes(b"x")
    ExifToolStripper(_script(tmp_path, "exiftool", "exit 0")).strip(photo, location_only=True)
    assert _no_keyboard(calls) and calls[0][1].get("timeout")
    slow = ExifToolStripper(_script(tmp_path, "slow-exiftool", "sleep 30"), timeout_seconds=0.2)
    with pytest.raises(RuntimeError, match="took too long"):
        slow.strip(photo, location_only=True)
