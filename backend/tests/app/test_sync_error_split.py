"""A pull can fail for a reason that waiting fixes (the network, a provider that throttles, a
slow answer) or for one it does not (not signed in, a folder that is not there, a provider
this version cannot pull from, a tool that is not installed, a full disk).

The second kind is a DomainError as well as a SyncError: the app's one handler answers it with
its status, and the worker fails its job at once instead of trying again for half an hour."""

import errno
import inspect
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.proton_drive import ProtonDrive
from photo_assistant.adapters.rclone_sync import classify_failure
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.api.routes import proton, remote_sources
from photo_assistant.app.sync_source import ProviderSync
from photo_assistant.app.worker import Worker
from photo_assistant.domain.errors import DomainError, NotFoundError, UnavailableError
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncDiskFullError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
    SyncToolMissingError,
    SyncUnsupportedError,
)
from tests.factories import NOW
from tests.proton_cloud import Cloud


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.mark.parametrize(
    ("error", "family"),
    [
        (SyncAuthError, UnavailableError),
        (SyncNotFoundError, NotFoundError),
        (SyncToolMissingError, UnavailableError),
        (SyncUnsupportedError, UnavailableError),
        (SyncDiskFullError, UnavailableError),
    ],
)
def test_what_waiting_cannot_fix_is_a_domain_error_with_the_status_it_always_had(
    error: type[SyncError], family: type[DomainError]
) -> None:
    assert issubclass(error, SyncError), "code that handles any pull failure still catches it"
    assert issubclass(error, family) and error.status == family.status


@pytest.mark.parametrize("error", [SyncError, SyncRateLimitedError])
def test_what_may_pass_stays_outside_the_hierarchy(error: type[SyncError]) -> None:
    assert not issubclass(error, DomainError)


@pytest.mark.parametrize(
    "error",
    [
        SyncAuthError("the login was refused"),
        SyncNotFoundError("folder 'x' not found on 'mega'"),
        SyncUnsupportedError("this version cannot pull from 'dropbox'"),
        SyncDiskFullError("the disk holding /data/staging is full"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_a_job_that_fails_for_one_of_them_is_not_tried_again(error: SyncError) -> None:
    repo = SqliteRepository(Database.open(":memory:"))

    def fail(payload: dict[str, object]) -> None:
        raise error

    repo.enqueue("scan_source", {})
    assert Worker(repo, {"scan_source": fail}, FixedClock()).run_until_idle() == 1
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 1 and failed["run_after"] is None
    assert failed["error"] == f"{type(error).__name__}: {error}"


def test_a_provider_this_version_cannot_pull_from(tmp_path: Path) -> None:
    with pytest.raises(SyncUnsupportedError) as refused:
        ProviderSync({}).pull(RemoteConfig("mega"), tmp_path / "staging", SyncOptions())
    assert str(refused.value) == "this version cannot pull from 'rclone'"


def test_a_full_disk_is_not_tried_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.photo("p1", "a.jpg")

    def full(self: Path, target: Path) -> Path:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "replace", full)
    with pytest.raises(SyncDiskFullError, match="is full: free some space, then pull again"):
        cloud.pull()


def test_a_pull_that_ran_out_of_time_is_tried_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.photo("p1", "a.jpg")
    drive, no_time = ProtonDrive(str(cloud.binary)), SyncOptions(timeout_seconds=0)

    with pytest.raises(SyncError, match="took too long and was stopped") as stopped:
        drive.pull(RemoteConfig.proton("/photos"), cloud.staging, no_time)

    assert not isinstance(stopped.value, DomainError), "a later pull continues: retry it"


def test_rclones_unknown_failures_and_throttling_may_pass() -> None:
    remote = RemoteConfig("mega")
    for line in ("connection reset by peer", "rate limit exceeded"):
        assert not isinstance(classify_failure(1, [line], remote), DomainError), line
    assert isinstance(classify_failure(1, ["HTTP error 401: Unauthorized"], remote), DomainError)
    assert isinstance(classify_failure(3, [], remote), NotFoundError)


@pytest.mark.parametrize("module", [proton, remote_sources])
def test_the_routes_no_longer_give_pull_errors_their_status_by_hand(module: object) -> None:
    source = inspect.getsource(module)  # type: ignore[arg-type]
    assert "HTTP_503_SERVICE_UNAVAILABLE" not in source
    assert "raise _" not in source
