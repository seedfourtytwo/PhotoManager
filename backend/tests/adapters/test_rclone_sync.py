"""RcloneSync with the real rclone binary and a local "remote" defined in a temp config file.

The remote folder is snapshotted before and after every pull: rclone only ever reads it.
"""

import json
import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.rclone_sync import RcloneSync, build_command, classify_failure
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
)
from tests.conftest import snapshot_tree

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parent.parent / "fixtures" / "photos"
needs_rclone = pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")
FAST = SyncOptions(tpslimit=0, transfers=2, checkers=2, retries=1, timeout_seconds=60)
# importable photos in the fixture set (videos, PDF, sidecars, .DS_Store are not pulled)
FIXTURE_MEDIA = {
    "IMG_1001.JPG",
    "IMG_1002.JPG",
    "IMG_1004.HEIC",
    "IMG_20180312_091500.jpg",
    "IMG_E1001.JPG",
    "Screenshot from 2026-07-03 15-21-27.png",
    "beach day 🌊.jpg",
    "empty.jpg",
    "grey-1x1.png",
    "not-an-image.jpg",
    "truncated.jpg",
    "nested/no-exif.jpg",
    "nested/deeper/IMG_1001 (Copy).JPG",
}


@pytest.fixture
def remote(tmp_path: Path) -> Iterator[tuple[RcloneSync, RemoteConfig, Path]]:
    """A "remote" that must be byte-identical when the test ends."""
    folder = tmp_path / "remote"
    shutil.copytree(FIXTURES, folder)
    (folder / "Été 2019").mkdir()
    shutil.copy(FIXTURES / "grey-1x1.png", folder / "Été 2019" / "Café ☕ 😀.PNG")
    config = tmp_path / "rclone.conf"
    config.write_text("[familycloud]\ntype = local\n")
    before = snapshot_tree(folder)
    yield RcloneSync(config_path=config), RemoteConfig("familycloud", str(folder)), folder
    assert snapshot_tree(folder) == before, "the remote was modified: pulls must be read-only"


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


@needs_rclone
def test_pull_mirrors_only_photos_including_unicode_names(
    remote: tuple[RcloneSync, RemoteConfig, Path], tmp_path: Path
) -> None:
    sync, config, _ = remote
    staging = tmp_path / "data" / "staging" / "1"
    report = sync.pull(config, staging, FAST)
    assert _files(staging) == FIXTURE_MEDIA | {"Été 2019/Café ☕ 😀.PNG"}
    assert (report.copied, report.updated, report.unchanged, report.errors) == (14, 0, 0, 0)
    assert report.bytes_transferred > 0


@needs_rclone
def test_a_second_pull_copies_nothing(
    remote: tuple[RcloneSync, RemoteConfig, Path], tmp_path: Path
) -> None:
    sync, config, _ = remote
    sync.pull(config, tmp_path / "staging", FAST)
    again = sync.pull(config, tmp_path / "staging", FAST)
    assert (again.copied, again.updated, again.unchanged) == (0, 0, 14)


@needs_rclone
def test_changed_remote_files_are_refreshed_and_deleted_ones_kept(tmp_path: Path) -> None:
    folder = tmp_path / "remote"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"\xff\xd8\xff first")
    (folder / "b.jpg").write_bytes(b"\xff\xd8\xff other")
    config = tmp_path / "rclone.conf"
    config.write_text("[r]\ntype = local\n")
    sync, remote = RcloneSync(config_path=config), RemoteConfig("r", str(folder))
    staging = tmp_path / "staging"
    sync.pull(remote, staging, FAST)
    (folder / "a.jpg").write_bytes(b"\xff\xd8\xff second version")
    os.utime(folder / "a.jpg", (1_900_000_000, 1_900_000_000))
    (folder / "b.jpg").unlink()
    before = snapshot_tree(folder)
    report = sync.pull(remote, staging, FAST)
    assert snapshot_tree(folder) == before
    assert (report.copied, report.updated) == (0, 1)
    assert (staging / "a.jpg").read_bytes() == b"\xff\xd8\xff second version"
    assert (staging / "b.jpg").exists(), "copy never deletes: the staging copy stays"


@needs_rclone
def test_a_missing_folder_on_the_remote_is_reported_as_not_found(
    remote: tuple[RcloneSync, RemoteConfig, Path], tmp_path: Path
) -> None:
    sync, config, folder = remote
    with pytest.raises(SyncNotFoundError, match="not found"):
        sync.pull(RemoteConfig("familycloud", str(folder / "nope")), tmp_path / "s", FAST)


@needs_rclone
def test_a_remote_not_set_up_in_rclone_says_how_to_fix_it(tmp_path: Path) -> None:
    config = tmp_path / "rclone.conf"
    config.write_text("")
    with pytest.raises(SyncAuthError, match="rclone config"):
        RcloneSync(config_path=config).pull(RemoteConfig("mega"), tmp_path / "s", FAST)


@needs_rclone
def test_list_remotes_reads_rclone_config(tmp_path: Path) -> None:
    config = tmp_path / "rclone.conf"
    config.write_text("[mega]\ntype = local\n\n[home server]\ntype = local\n")
    assert RcloneSync(config_path=config).list_remotes() == ["home server", "mega"]


def test_a_missing_rclone_binary_is_explained(tmp_path: Path) -> None:
    sync = RcloneSync(binary=str(tmp_path / "no-rclone"))
    with pytest.raises(SyncError, match="rclone is not installed"):
        sync.pull(RemoteConfig("mega"), tmp_path / "s", FAST)
    with pytest.raises(SyncError, match="rclone is not installed"):
        sync.list_remotes()


# --- a scripted stand-in for rclone: partial failures, throttling, timeouts ------------------


def _fake_rclone(tmp_path: Path, stderr_lines: list[dict[str, object]], code: int) -> Path:
    log = tmp_path / "fake.log"
    log.write_text("\n".join(json.dumps(line) for line in stderr_lines) + "\n")
    script = tmp_path / "fake-rclone"
    script.write_text(f'#!/bin/sh\necho "$@" > "{tmp_path}/args"\ncat "{log}" >&2\nexit {code}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_a_partial_pull_returns_counts_and_errors(tmp_path: Path) -> None:
    lines: list[dict[str, object]] = [
        {"level": "info", "msg": "Copied (new)", "object": "a.jpg"},
        {"level": "error", "msg": "Failed to copy: read error", "object": "b.jpg"},
        {"level": "info", "msg": "stats", "stats": {"errors": 1, "bytes": 10, "checks": 3}},
    ]
    sync = RcloneSync(binary=str(_fake_rclone(tmp_path, lines, 6)))
    report = sync.pull(RemoteConfig("mega"), tmp_path / "s", FAST)
    assert (report.copied, report.unchanged, report.errors, report.bytes_transferred) == (
        1,
        3,
        1,
        10,
    )
    assert report.partial
    assert report.error_messages == ("b.jpg: Failed to copy: read error",)


def test_throttling_is_reported_as_rate_limited(tmp_path: Path) -> None:
    lines: list[dict[str, object]] = [
        {"level": "error", "msg": "couldn't list files: HTTP error 429: Too Many Requests"}
    ]
    sync = RcloneSync(binary=str(_fake_rclone(tmp_path, lines, 7)))
    with pytest.raises(SyncRateLimitedError, match="later"):
        sync.pull(RemoteConfig("mega"), tmp_path / "s", FAST)


def test_the_command_is_copy_with_throttling_and_a_media_filter(tmp_path: Path) -> None:
    sync = RcloneSync(binary=str(_fake_rclone(tmp_path, [], 0)))
    sync.pull(RemoteConfig("mega", "Camera"), tmp_path / "s", SyncOptions())
    args = (tmp_path / "args").read_text().split()
    assert args[:3] == ["copy", "mega:Camera", str(tmp_path / "s")]
    assert "--tpslimit" in args and "--filter-from" in args and "--ignore-case" in args


def test_a_pull_that_runs_too_long_is_stopped(tmp_path: Path) -> None:
    script = tmp_path / "slow-rclone"
    script.write_text("#!/bin/sh\nsleep 5\n")
    script.chmod(0o755)
    options = SyncOptions(timeout_seconds=0.2)
    with pytest.raises(SyncError, match="took longer"):
        RcloneSync(binary=str(script)).pull(RemoteConfig("mega"), tmp_path / "s", options)


# --- pure parts ------------------------------------------------------------------------------


def test_build_command_never_writes_to_the_remote() -> None:
    args = build_command("rclone", RemoteConfig("m", "p"), Path("/s"), Path("/f"), SyncOptions())
    assert args[1] == "copy"
    assert args[2] == "m:p", "the remote is always the *source* of the copy"
    forbidden = {"sync", "move", "moveto", "delete", "purge", "rmdirs", "bisync"}
    assert not forbidden & set(args)
    assert not [a for a in args if a.startswith(("--delete", "--remove", "--backup-dir"))]
    assert args[args.index("--tpslimit") + 1] == "4"


def test_build_command_passes_the_config_file_and_omits_zero_tpslimit() -> None:
    options = SyncOptions(tpslimit=0)
    args = build_command("rclone", RemoteConfig("m"), Path("/s"), Path("/f"), options, Path("/c"))
    assert args[args.index("--config") + 1] == "/c"
    assert "--tpslimit" not in args


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("couldn't login: Object (typically, node or user) not found", SyncAuthError),
        ("HTTP error 401: Unauthorized", SyncAuthError),
        ("invalid credentials", SyncAuthError),
        ("2FA code required", SyncAuthError),
        ("EAGAIN (-3): A temporary congestion or server malfunction", SyncRateLimitedError),
        ("rate limit exceeded", SyncRateLimitedError),
        ("error reading source root directory: directory not found", SyncNotFoundError),
        ("something odd", SyncError),
    ],
)
def test_classify_failure_maps_messages_to_plain_errors(
    message: str, expected: type[SyncError]
) -> None:
    error = classify_failure(2, [message], RemoteConfig("mega"))
    assert type(error) is expected
    assert "mega" in str(error)


def test_exit_code_three_means_not_found() -> None:
    assert type(classify_failure(3, [], RemoteConfig("m"))) is SyncNotFoundError
