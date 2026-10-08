"""Headless bootstrap: create the first admin from the command line."""

from datetime import timedelta
from pathlib import Path

import pytest

from photo_assistant import __main__ as cli
from photo_assistant.api.settings import get_settings
from photo_assistant.app.accounts import AccountLockedError
from photo_assistant.domain.access import LOCK_AFTER_FAILED_PINS, Role

PIN = "1234"


@pytest.fixture
def data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    get_settings.cache_clear()
    monkeypatch.setenv("PA_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("PA_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("PA_ARGON2_MEMORY_KIB", "64")
    yield tmp_path / "data"
    get_settings.cache_clear()


def test_create_user_prompts_for_the_pin_twice(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PIN, PIN])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    assert "Created admin 'c'" in capsys.readouterr().out
    services = cli.build_services(get_settings())
    try:
        found = services.repo.find_user_by_username("c")
        assert found is not None and found[0].role is Role.ADMIN
    finally:
        services.close()


def test_create_user_refuses_mismatched_or_malformed_pins(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PIN, "4321", "12345", "12345"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c"]) == 2
    assert "do not match" in capsys.readouterr().err
    assert cli.main(["create-user", "c"]) == 2
    assert "4 digits" in capsys.readouterr().err


def test_set_pin_gives_an_account_a_new_pin_without_a_session(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PIN, PIN, "5678", "5678", "5678", "8765", "abcd", "abcd", "5678", "5678"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    assert cli.main(["set-pin", "C"]) == 0
    assert "New PIN set for 'c'" in capsys.readouterr().out
    services = cli.build_services(get_settings())
    try:
        services.accounts.login("c", "5678", "127.0.0.1")
    finally:
        services.close()
    assert cli.main(["set-pin", "c"]) == 2
    assert "do not match" in capsys.readouterr().err
    assert cli.main(["set-pin", "c"]) == 2
    assert "4 digits" in capsys.readouterr().err
    assert cli.main(["set-pin", "nobody"]) == 2
    assert "no such user" in capsys.readouterr().err


def test_set_pin_unlocks_an_account_locked_by_wrong_pins(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The way back in for an only admin who is locked out: nobody else can unlock them."""
    answers = iter([PIN, PIN, "5678", "5678"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    services = cli.build_services(get_settings())
    try:
        clock = services.clock.now()
        for n in range(LOCK_AFTER_FAILED_PINS):  # spread out: never ten in one 15-minute window
            at = clock - timedelta(hours=LOCK_AFTER_FAILED_PINS - n)
            assert services.repo.record_login_attempt("c", "10.0.0.1", at, at).allowed
        with pytest.raises(AccountLockedError):
            services.accounts.login("c", PIN, "127.0.0.1")
    finally:
        services.close()
    assert cli.main(["set-pin", "c"]) == 0
    assert "unlocked" in capsys.readouterr().out
    services = cli.build_services(get_settings())
    try:
        user, _ = services.accounts.login("c", "5678", "127.0.0.1")
        assert not user.locked
    finally:
        services.close()


# --- ops commands are subcommands of the main CLI (docs/wiring/ops.md) -----------------------


def test_doctor_runs_from_the_main_cli(data_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code in (0, 1)  # 1 = something to fix on this machine (e.g. a missing tool)
    assert "exiftool" in out.lower()


def test_export_and_verify_library_from_the_main_cli(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.synthetic import write_photo

    pics = tmp_path / "pics"
    write_photo(pics / "a.jpg", seed=1)
    assert cli.main(["import", str(pics)]) == 0
    destination = tmp_path / "copy"
    assert cli.main(["export-library", str(destination)]) == 0
    assert cli.main(["verify-library", str(destination)]) == 0
    assert "1" in capsys.readouterr().out


def test_a_cli_import_leaves_the_servers_other_jobs_in_the_queue(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the server running, its backups, scans and ML jobs are not the CLI's to run."""
    from tests.synthetic import write_photo

    services = cli.build_services(get_settings())
    try:
        for kind in ("backup_due", "purge_trash", "scan_source", "cluster_faces"):
            services.repo.enqueue(kind, {"source_id": 999} if kind == "scan_source" else {})
    finally:
        services.close()
    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    assert cli.main(["import", str(tmp_path / "pics")]) == 0
    assert "Making 3 " in capsys.readouterr().out, "its own preview, places and groups"
    services = cli.build_services(get_settings())
    try:
        waiting = [(j["kind"], j["attempts"]) for j in services.repo.list_jobs("queued")]
        done = {j["kind"] for j in services.repo.list_jobs("done")}
        failed = services.repo.list_jobs("failed")
    finally:
        services.close()
    assert waiting == [
        ("backup_due", 0),
        ("purge_trash", 0),
        ("scan_source", 0),
        ("cluster_faces", 0),
    ]
    assert done == {"preview", "geocode", "group"} and failed == []


def test_backup_list_from_the_main_cli(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["backup", "list"]) == 2
    assert "import some photos first" in capsys.readouterr().err
    from tests.synthetic import write_photo

    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    assert cli.main(["import", str(tmp_path / "pics")]) == 0
    assert cli.main(["backup", "list"]) == 0


def test_backup_settings_come_from_the_main_settings(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PA_RESTIC_BINARY", "/nowhere/restic")
    get_settings.cache_clear()
    assert get_settings().ops.restic_binary == "/nowhere/restic"


def test_ml_backfill_reports_missing_models(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["ml-backfill"]) == 0
    out = capsys.readouterr().out
    assert "Queued" in out and "missing" in out
