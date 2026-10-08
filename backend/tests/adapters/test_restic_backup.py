"""The restic adapter against the real restic binary and a repository in a temp folder."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from photo_assistant.adapters.restic_backup import (
    ResticBackup,
    classify_failure,
    parse_restic_time,
)
from photo_assistant.domain.backup import BACKUP_FOLDERS, Retention
from photo_assistant.ports.backup import (
    BackupError,
    BackupToolMissingError,
    IncompleteBackupError,
    PasswordFileError,
    RepositoryLockedError,
    RepositoryNotFoundError,
    RepositoryRef,
    WrongPasswordError,
)
from tests.conftest import snapshot_tree

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing"),
]


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    for n in range(5):
        photo = root / "originals" / "2020" / "01" / f"{n:064x}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(bytes([n]) * 50_000 + f"photo {n}".encode())
        photo.chmod(0o444)
    (root / "derived" / "thumb").mkdir(parents=True)
    (root / "derived" / "thumb" / "x.webp").write_bytes(b"rebuildable")
    (root / "recipes").mkdir()
    (root / "recipes" / "1.json").write_text('{"rotate": 90}')
    return root


@pytest.fixture
def repo(tmp_path: Path) -> RepositoryRef:
    password = tmp_path / "secrets" / "restic-password"
    password.parent.mkdir()
    password.write_text("correct horse battery staple\n")
    return RepositoryRef(str(tmp_path / "backup-disk" / "photos"), password)


@pytest.fixture
def engine(tmp_path: Path) -> ResticBackup:
    return ResticBackup(cache_dir=tmp_path / "restic-cache")


def _snapshot_count(repo: RepositoryRef) -> int:
    done = subprocess.run(
        [
            "restic",
            "-r",
            repo.location,
            "--password-file",
            str(repo.password_file),
            "--json",
            "snapshots",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return len(json.loads(done.stdout))


def _ready(engine: ResticBackup, repo: RepositoryRef) -> None:
    Path(repo.location).parent.mkdir(parents=True, exist_ok=True)
    assert engine.ensure_repository(repo) is True


def test_creates_the_repository_once(engine: ResticBackup, repo: RepositoryRef) -> None:
    _ready(engine, repo)
    assert engine.ensure_repository(repo) is False
    assert (Path(repo.location) / "config").is_file()


def test_never_creates_a_repository_where_an_unplugged_disk_should_be(
    engine: ResticBackup, repo: RepositoryRef
) -> None:
    with pytest.raises(RepositoryNotFoundError, match="plug in"):
        engine.ensure_repository(repo)
    assert not Path(repo.location).parent.exists()


def test_backup_is_incremental_and_skips_thumbnails(
    engine: ResticBackup, repo: RepositoryRef, library: Path, tmp_path: Path
) -> None:
    _ready(engine, repo)
    first = engine.backup(repo, library, BACKUP_FOLDERS)
    assert first.files_new == 6 and first.bytes_added > 0
    new_photo = library / "originals" / "2020" / "02" / f"{9:064x}.jpg"
    new_photo.parent.mkdir()
    new_photo.write_bytes(b"one more photo")
    second = engine.backup(repo, library, BACKUP_FOLDERS)
    assert (second.files_new, second.files_changed) == (1, 0)
    assert second.bytes_added < first.bytes_added / 10, "only the new data is sent"

    latest = engine.latest_snapshot(repo)
    assert latest is not None and latest.snapshot_id == second.snapshot_id
    everything = tmp_path / "restored"
    engine.restore(
        repo, second.snapshot_id, ["originals", "recipes", "derived", "db-snapshot"], everything
    )
    assert (everything / "recipes" / "1.json").read_text() == '{"rotate": 90}'
    assert (everything / new_photo.relative_to(library)).read_bytes() == b"one more photo"
    assert not (everything / "derived").exists(), "thumbnails are rebuildable, not backed up"
    assert engine.repository_size(repo) > 0


def test_restore_only_brings_back_what_was_asked(
    engine: ResticBackup, repo: RepositoryRef, library: Path, tmp_path: Path
) -> None:
    _ready(engine, repo)
    snap = engine.backup(repo, library, BACKUP_FOLDERS)
    wanted = f"originals/2020/01/{2:064x}.jpg"
    engine.restore(repo, snap.snapshot_id, [wanted], tmp_path / "sample")
    restored = [p for p in (tmp_path / "sample").rglob("*") if p.is_file()]
    assert [p.relative_to(tmp_path / "sample").as_posix() for p in restored] == [wanted]
    engine.restore(repo, snap.snapshot_id, [], tmp_path / "nothing")
    assert not (tmp_path / "nothing").exists(), "an empty list never means 'everything'"


def test_forget_applies_retention_and_prunes(
    engine: ResticBackup, repo: RepositoryRef, library: Path
) -> None:
    _ready(engine, repo)
    for n in range(3):
        (library / "recipes" / f"extra{n}.json").write_text(str(n))
        engine.backup(repo, library, BACKUP_FOLDERS)
    assert _snapshot_count(repo) == 3
    engine.forget(repo, Retention(daily=1, weekly=0, monthly=0))
    assert _snapshot_count(repo) == 1, "three snapshots on one day: keep the last"


def test_check_passes_and_catches_damaged_data(
    engine: ResticBackup, repo: RepositoryRef, library: Path
) -> None:
    _ready(engine, repo)
    engine.backup(repo, library, BACKUP_FOLDERS)
    engine.check(repo)
    engine.check(repo, read_data_subset="100%")
    packs = [p for p in (Path(repo.location) / "data").rglob("*") if p.is_file()]
    pack = max(packs, key=lambda p: p.stat().st_size)
    pack.chmod(0o644)
    data = bytearray(pack.read_bytes())
    data[100] ^= 0xFF
    pack.write_bytes(bytes(data))
    with pytest.raises(BackupError):
        engine.check(repo, read_data_subset="100%")
    with pytest.raises(BackupError, match="subset"):
        engine.check(repo, read_data_subset="all of it")


def test_wrong_password_is_reported_as_such(
    engine: ResticBackup, repo: RepositoryRef, library: Path, tmp_path: Path
) -> None:
    _ready(engine, repo)
    wrong = tmp_path / "wrong"
    wrong.write_text("nope\n")
    bad = RepositoryRef(repo.location, wrong)
    with pytest.raises(WrongPasswordError, match="wrong password"):
        engine.ensure_repository(bad)
    with pytest.raises(WrongPasswordError):
        engine.backup(bad, library, BACKUP_FOLDERS)


def test_missing_password_file_and_missing_restic(
    repo: RepositoryRef, library: Path, tmp_path: Path
) -> None:
    missing = RepositoryRef(repo.location, tmp_path / "no-such-file")
    with pytest.raises(PasswordFileError, match="password file"):
        ResticBackup().ensure_repository(missing)
    with pytest.raises(BackupToolMissingError, match="apt install restic"):
        ResticBackup(binary="restic-not-installed").ensure_repository(repo)


def test_probe_says_an_empty_folder_holds_no_repository(
    engine: ResticBackup, repo: RepositoryRef
) -> None:
    Path(repo.location).mkdir(parents=True)
    reason = engine.probe(repo)
    assert reason is not None and "no backup repository" in reason
    assert list(Path(repo.location).iterdir()) == [], "a probe never creates anything"


def test_probe_finds_an_existing_repository_without_locking_it(
    engine: ResticBackup, repo: RepositoryRef
) -> None:
    _ready(engine, repo)
    locks = Path(repo.location) / "locks"
    before = locks.stat().st_mtime_ns
    locks.chmod(0o555)  # a read-only repository: any attempt to take a lock would fail
    try:
        assert engine.probe(repo) is None
    finally:
        locks.chmod(0o755)
    assert list(locks.iterdir()) == [] and locks.stat().st_mtime_ns == before


def test_probe_raises_on_a_wrong_password(
    engine: ResticBackup, repo: RepositoryRef, tmp_path: Path
) -> None:
    _ready(engine, repo)
    wrong = tmp_path / "wrong"
    wrong.write_text("nope\n")
    with pytest.raises(WrongPasswordError):
        engine.probe(RepositoryRef(repo.location, wrong))


def _failing_restic(tmp_path: Path, exit_code: int, message: str) -> ResticBackup:
    script = tmp_path / "restic-fails"
    script.write_text(f"#!/bin/sh\necho '{message}' >&2\nexit {exit_code}\n")
    script.chmod(0o755)
    return ResticBackup(binary=str(script))


def test_probe_treats_an_unanswering_remote_as_out_of_reach(tmp_path: Path) -> None:
    engine = _failing_restic(tmp_path, 1, "Fatal: unable to open repository: connection refused")
    reason = engine.probe(RepositoryRef("rclone:nas:photos", tmp_path / "pw"))
    assert reason is not None and "connection refused" in reason


def test_probe_raises_on_a_generic_failure_of_a_local_repository(tmp_path: Path) -> None:
    engine = _failing_restic(tmp_path, 1, "Fatal: something broke")
    with pytest.raises(BackupError, match="something broke"):
        engine.probe(RepositoryRef(str(tmp_path / "disk" / "photos"), tmp_path / "pw"))


def test_nothing_to_back_up(engine: ResticBackup, repo: RepositoryRef, tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="nothing to back up"):
        engine.backup(repo, tmp_path / "empty", BACKUP_FOLDERS)


def test_our_environment_can_not_redirect_restic(
    monkeypatch: pytest.MonkeyPatch, engine: ResticBackup, repo: RepositoryRef, library: Path
) -> None:
    monkeypatch.setenv("RESTIC_REPOSITORY", "/somewhere/else")
    monkeypatch.setenv("RESTIC_PASSWORD", "leaked")
    _ready(engine, repo)
    engine.backup(repo, library, BACKUP_FOLDERS)
    assert not Path("/somewhere/else").exists()


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone missing")
def test_rclone_remote_repository(repo: RepositoryRef, library: Path, tmp_path: Path) -> None:
    """restic's rclone backend, with a 'local' rclone remote defined in the environment."""
    engine = ResticBackup(extra_env={"RCLONE_CONFIG_PATEST_TYPE": "local"})
    remote = RepositoryRef(f"rclone:patest:{tmp_path / 'remote-repo'}", repo.password_file)
    assert engine.ensure_repository(remote) is True
    snap = engine.backup(remote, library, BACKUP_FOLDERS)
    assert snap.files_new == 6
    assert (tmp_path / "remote-repo" / "config").is_file()


def test_failed_backups_never_touch_the_library(
    engine: ResticBackup, repo: RepositoryRef, library: Path, tmp_path: Path
) -> None:
    before = snapshot_tree(library)
    wrong = RepositoryRef(repo.location, tmp_path / "missing-password")
    for attempt in (
        lambda: engine.ensure_repository(repo),  # disk not plugged in
        lambda: engine.backup(repo, library, BACKUP_FOLDERS),  # no repository
        lambda: engine.backup(wrong, library, BACKUP_FOLDERS),
        lambda: ResticBackup(binary="nope").backup(repo, library, BACKUP_FOLDERS),
    ):
        with pytest.raises(BackupError):
            attempt()
    assert snapshot_tree(library) == before


@pytest.mark.parametrize(
    ("code", "stderr", "error"),
    [
        (12, "", WrongPasswordError),
        (1, "Fatal: wrong password or no key found", WrongPasswordError),
        (10, "", RepositoryNotFoundError),
        (1, "Is there a repository at the following location?", RepositoryNotFoundError),
        (11, "", RepositoryLockedError),
        (1, "unable to create lock: repository is already locked by PID 1", RepositoryLockedError),
        (3, "error: open x: permission denied", IncompleteBackupError),
        (1, "Resolving password failed: Fatal: /x does not exist", PasswordFileError),
        (1, "rclone: noise\nsomething else broke", BackupError),
    ],
)
def test_failure_mapping(code: int, stderr: str, error: type[BackupError]) -> None:
    result = classify_failure(code, stderr, RepositoryRef("/r", Path("/p")))
    assert type(result) is error
    assert "/r" in str(result) or "/p" in str(result) or "could not be read" in str(result)


def test_generic_failures_keep_the_useful_part_of_stderr() -> None:
    result = classify_failure(1, "rclone: noise\nFatal: boom", RepositoryRef("/r", Path("/p")))
    assert "Fatal: boom" in str(result) and "noise" not in str(result)
    assert "no details" in str(classify_failure(1, "", RepositoryRef("/r", Path("/p"))))


def test_restic_times() -> None:
    assert parse_restic_time("2026-09-29T20:48:25.677092329Z").isoformat() == (
        "2026-09-29T20:48:25.677092+00:00"
    )
    assert parse_restic_time("2026-09-29T22:48:25+02:00").isoformat() == (
        "2026-09-29T20:48:25+00:00"
    )
    with pytest.raises(BackupError):
        parse_restic_time("yesterday")
