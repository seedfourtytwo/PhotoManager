"""What kind of trouble a backup error is, read from the text it was stored with (contract
v1.14 ``error_kind``). The cases are the texts our adapters and the tools really produce."""

import pytest

from photo_assistant.domain.backup_errors import ErrorKind, error_kind


@pytest.mark.parametrize(
    "text",
    [
        # app/backup.py, a run skipped because the place was away
        "USB disk is not connected: plug it in and the backup starts by itself",
        "Home server cannot be reached right now: it is backed up as soon as it can be",
        # app/backup.py MIRROR_WAIT
        "the copy on Proton Drive waits until this computer is online and the backup disk is "
        "connected",
        # restic_backup.classify_failure, RepositoryNotFoundError
        "no backup repository at /media/c/USB: is the disk plugged in / the server reachable?",
        # raw restic and network errors (tests/adapters/test_restic_backup.py, test_backup_service)
        "restic failed (exit 1) for /r: Fatal: unable to open repository: connection refused",
        "measuring the backup failed: network is unreachable",
        "dial tcp: lookup nas.local: no such host",
        "Post https://x/: net/http: TLS handshake timeout",
        # proton_mirror.py
        "backup folder not found: /media/c/USB/photo-assistant-backup",
    ],
)
def test_a_place_that_is_away_or_cannot_be_reached_is_unreachable(text: str) -> None:
    assert error_kind(text) is ErrorKind.UNREACHABLE


@pytest.mark.parametrize(
    "text",
    [
        "restic failed (exit 1) for /media/c/USB: Fatal: unable to save snapshot: "
        "write /media/c/USB/data/3f/3fa1: no space left on device",
        "OSError: [Errno 28] No space left on device",
        # proton_drive.py _disk_error
        "the disk holding /data/staging is full: free some space, then pull again",
        "[Errno 122] Disk quota exceeded: '/media/c/USB/data'",
    ],
)
def test_a_full_disk_is_disk_full(text: str) -> None:
    assert error_kind(text) is ErrorKind.DISK_FULL


@pytest.mark.parametrize(
    "text",
    [
        # restic_backup.classify_failure: WrongPasswordError, PasswordFileError
        "wrong password for the backup at /media/c/USB: check /data/keys/usb.key",
        "cannot read the password file /data/keys/usb.key",
        # proton_drive.py, SyncAuthError
        "Proton Drive is not signed in on this machine: run 'proton-drive auth login' and try "
        "again",
        "Proton Drive is not signed in: run 'x'",
        # rclone_sync.py _AUTH
        "couldn't login: 401 Unauthorized",
        "Fatal error: didn't find section in config file",
    ],
)
def test_a_password_or_sign_in_problem_is_auth(text: str) -> None:
    assert error_kind(text) is ErrorKind.AUTH


@pytest.mark.parametrize(
    "text",
    [
        # restic_backup.classify_failure, RepositoryLockedError
        "the backup at /media/c/USB is locked by another run; if none is running, "
        "run 'restic unlock' on it",
        "restic failed (exit 1) for /r: unable to create lock: repository is already locked by "
        "PID 1",
    ],
)
def test_a_repository_held_by_another_run_is_locked(text: str) -> None:
    assert error_kind(text) is ErrorKind.LOCKED


@pytest.mark.parametrize(
    "text",
    [
        "restic failed (exit 1) for /r: Fatal: something broke",
        "some library files could not be read, the snapshot is incomplete: error: open x: "
        "permission denied",
        "RuntimeError",
        "3 of 20 photos did not match their hash",
    ],
)
def test_anything_else_is_unknown(text: str) -> None:
    assert error_kind(text) is ErrorKind.UNKNOWN


def test_no_error_has_no_kind() -> None:
    assert error_kind(None) is None
    assert error_kind("") is None


def test_the_kinds_are_the_contract_values() -> None:
    assert [k.value for k in ErrorKind] == ["unreachable", "disk_full", "auth", "locked", "unknown"]
