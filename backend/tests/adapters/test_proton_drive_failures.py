"""ProtonDrive when things go wrong mid-pull: nothing arrives, the tool goes away, the disk
refuses, the pull is cut off. Same stand-in CLI as test_proton_drive.py."""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from photo_assistant.ports.sync import SyncAuthError, SyncError
from tests.proton_cloud import Cloud


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Cloud:
    return Cloud(tmp_path, monkeypatch)


def _photos(cloud: Cloud, count: int) -> list[str]:
    for n in range(count):
        cloud.photo(f"p{n}", f"{n}.jpg")
    return [f"p{n}" for n in range(count)]


def _break_downloads(monkeypatch: pytest.MonkeyPatch, error: Exception) -> list[list[str]]:
    """Listing still works; every download command fails with ``error``. Returns the attempts."""
    real, attempts = subprocess.run, []

    def run(args: list[str], **kwargs: Any) -> Any:
        if "download" not in args:
            return real(args, **kwargs)
        attempts.append(args)
        raise error

    monkeypatch.setattr(subprocess, "run", run)
    return attempts


# --- nothing could be pulled ----------------------------------------------------------------------


def test_a_pull_where_every_download_fails_is_an_error_not_a_clean_run(cloud: Cloud) -> None:
    cloud.state["fail"] = _photos(cloud, 9)
    cloud.save()
    with pytest.raises(SyncError, match=r"0\.jpg: the download failed"):
        cloud.pull()
    assert cloud.staged() == []


def test_failing_batches_stop_being_retried_one_photo_at_a_time(cloud: Cloud) -> None:
    cloud.state["fail"] = _photos(cloud, 15)
    cloud.save()
    with pytest.raises(SyncError):
        cloud.pull()
    # three batches are taken apart (1 + 3 calls each), the last two are tried once
    assert len(cloud.downloads()) == 14


def test_a_photo_that_fails_among_good_ones_is_still_only_a_partial_pull(cloud: Cloud) -> None:
    uids = _photos(cloud, 12)
    cloud.state["fail"] = uids[1:]
    cloud.save()
    report = cloud.pull()
    assert (report.copied, report.errors) == (1, 11)
    assert cloud.staged() == ["0.jpg"]


def test_a_tool_that_went_missing_stops_the_pull_at_once(
    cloud: Cloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    _photos(cloud, 9)
    attempts = _break_downloads(monkeypatch, FileNotFoundError("proton-drive"))
    with pytest.raises(SyncError, match="not installed"):
        cloud.pull()
    assert len(attempts) == 1


def test_a_download_that_takes_too_long_stops_the_pull_at_once(
    cloud: Cloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    _photos(cloud, 9)
    attempts = _break_downloads(monkeypatch, subprocess.TimeoutExpired("proton-drive", 1))
    with pytest.raises(SyncError, match="took too long"):
        cloud.pull()
    assert len(attempts) == 1


# --- a pull that is cut off -----------------------------------------------------------------------


def test_photos_that_landed_before_the_pull_was_cut_off_are_not_fetched_twice(
    cloud: Cloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The batch fails, the photos are asked for one by one, and the session ends after the
    first of them arrived: that one is remembered."""
    _photos(cloud, 3)
    cloud.state["crash_on_batch"] = True
    cloud.save()
    real, downloads = subprocess.run, 0

    def run(args: list[str], **kwargs: Any) -> Any:
        nonlocal downloads
        downloads += "download" in args
        if downloads == 3:
            cloud.state["signed_in"] = False
            cloud.save()
        return real(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(SyncAuthError):
        cloud.pull()
    assert cloud.staged() == ["0.jpg"]
    monkeypatch.undo()
    monkeypatch.setenv("PA_FAKE_PROTON", str(cloud.state_file))
    cloud.state["signed_in"] = True
    cloud.save()
    report = cloud.pull()
    assert (report.copied, report.unchanged) == (2, 1)
    assert cloud.staged() == ["0.jpg", "1.jpg", "2.jpg"]
