"""Which job failures get another try (ARCHITECTURE, "Retries wait").

A DomainError says "the same job would fail the same way": a tool or a model that is not
installed, a backup target that was deleted. The worker fails those at once. What may pass by
waiting (the network, a locked repository, an unplugged disk, a slow tool) is kept outside the
hierarchy on purpose and is retried with a growing wait.
"""

from pathlib import Path

import pytest

from photo_assistant.adapters.proton_drive import ProtonDrive
from photo_assistant.adapters.rclone_sync import RcloneSync
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.adapters.tool_runner import ToolTimeoutError
from photo_assistant.app.backup import BACKUP_JOB, UnknownTargetError
from photo_assistant.app.worker import Worker
from photo_assistant.domain.errors import DomainError
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.ai import AIUnavailableError
from photo_assistant.ports.backup import (
    BackupError,
    BackupToolMissingError,
    IncompleteBackupError,
    MirrorError,
    RepositoryLockedError,
    RepositoryNotFoundError,
    WrongPasswordError,
)
from photo_assistant.ports.ml import ModelFormatError, ModelUnavailableError
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
    SyncToolMissingError,
)
from tests.app.test_backup import World
from tests.fakes import FakeClock


def _run_once(repo: SqliteRepository, error: Exception) -> None:
    def fail(payload: dict[str, object]) -> None:
        raise error

    repo.enqueue("job", {})
    assert Worker(repo, {"job": fail}, FakeClock()).run_until_idle() == 1


@pytest.mark.parametrize(
    "error",
    [
        UnknownTargetError("no backup target 7"),
        SyncToolMissingError("rclone is not installed on this machine"),
        SyncAuthError("the login was refused"),
        SyncNotFoundError("folder 'x' not found on 'mega'"),
        BackupToolMissingError("'restic' is not installed: sudo apt install restic"),
        ModelUnavailableError("model file clip.onnx is missing: run `just models`"),
        ModelFormatError("clip.onnx: expected 512 dimensions"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_what_waiting_cannot_fix_fails_at_once(repo: SqliteRepository, error: Exception) -> None:
    _run_once(repo, error)
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 1 and failed["run_after"] is None
    assert failed["error"] == f"{type(error).__name__}: {error}"


@pytest.mark.parametrize(
    "error",
    [
        SyncError("pulling from 'mega' failed: connection reset"),
        SyncRateLimitedError("the provider is throttling"),
        BackupError("restic did not answer within 5 min"),
        RepositoryLockedError("the repository is locked by another restic"),
        RepositoryNotFoundError("no repository at /media/usb: is the disk plugged in?"),
        WrongPasswordError("wrong password"),
        IncompleteBackupError("some files could not be read"),
        MirrorError("the copy on Proton Drive failed"),
        ToolTimeoutError("'exiftool' did not finish within 30 s"),
        AIUnavailableError("the AI server did not answer in time"),
        ConnectionError("offline"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_what_may_pass_is_retried_after_a_wait(repo: SqliteRepository, error: Exception) -> None:
    assert not isinstance(error, DomainError)
    _run_once(repo, error)
    (waiting,) = repo.list_jobs("queued")
    assert waiting["attempts"] == 1 and waiting["run_after"] is not None


def test_a_backup_job_for_a_target_deleted_meanwhile_fails_at_once(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    world = World(tmp_path)
    repo.enqueue(BACKUP_JOB, {"target_id": 99})
    assert Worker(repo, world.service.job_handlers(), FakeClock()).run_until_idle() == 1
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 1 and failed["error"] == "UnknownTargetError: no backup target 99"


def test_a_pull_without_its_tool_is_an_error_waiting_cannot_fix(tmp_path: Path) -> None:
    """Still a SyncError (routes answer 503, the import history records it), now one the worker
    does not retry for six minutes before giving up."""
    options = SyncOptions()
    rclone = RcloneSync(binary=str(tmp_path / "no-rclone"))
    with pytest.raises(SyncToolMissingError, match="rclone is not installed") as missing:
        rclone.pull(RemoteConfig("mega"), tmp_path / "staging", options)
    assert isinstance(missing.value, SyncError) and isinstance(missing.value, DomainError)
    with pytest.raises(SyncToolMissingError, match="rclone is not installed"):
        rclone.list_remotes()
    proton = ProtonDrive(str(tmp_path / "no-proton-drive"))
    with pytest.raises(SyncToolMissingError, match="not installed") as absent:
        proton.pull(RemoteConfig.proton("/photos"), tmp_path / "staging", options)
    assert isinstance(absent.value, SyncError) and isinstance(absent.value, DomainError)
