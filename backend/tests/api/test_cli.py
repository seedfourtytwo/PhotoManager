"""Headless bootstrap: create the first admin from the command line."""

import dataclasses
import getpass
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from photo_assistant import __main__ as cli
from photo_assistant.api.cli_command import Command
from photo_assistant.api.services import build_services
from photo_assistant.api.settings import get_settings
from photo_assistant.app.accounts import AccountLockedError
from photo_assistant.domain.access import LOCK_AFTER_FAILED_PINS, Role

PIN = "1234"


@pytest.fixture
def data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
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
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    assert "Created admin 'c'" in capsys.readouterr().out
    services = build_services(get_settings())
    try:
        found = services.repo.find_user_by_username("c")
        assert found is not None and found[0].role is Role.ADMIN
    finally:
        services.close()


def test_create_user_refuses_mismatched_or_malformed_pins(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PIN, "4321", "12345", "12345"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c"]) == 2
    assert "do not match" in capsys.readouterr().err
    assert cli.main(["create-user", "c"]) == 2
    assert "4 digits" in capsys.readouterr().err


def test_set_pin_gives_an_account_a_new_pin_without_a_session(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PIN, PIN, "5678", "5678", "5678", "8765", "abcd", "abcd", "5678", "5678"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    assert cli.main(["set-pin", "C"]) == 0
    assert "New PIN set for 'c'" in capsys.readouterr().out
    services = build_services(get_settings())
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
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    services = build_services(get_settings())
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
    services = build_services(get_settings())
    try:
        user, _ = services.accounts.login("c", "5678", "127.0.0.1")
        assert not user.locked
    finally:
        services.close()


# --- ops commands are subcommands of the main CLI -----------------------------------------------


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

    services = build_services(get_settings())
    try:
        for kind in ("backup_due", "purge_trash", "scan_source", "cluster_faces"):
            services.repo.enqueue(kind, {"source_id": 999} if kind == "scan_source" else {})
    finally:
        services.close()
    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    assert cli.main(["import", str(tmp_path / "pics")]) == 0
    assert "Making 3 " in capsys.readouterr().out, "its own preview, places and groups"
    services = build_services(get_settings())
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


def _source_owners() -> list[int | None]:
    services = build_services(get_settings())
    try:
        return [s.owner_id for s in services.repo.list_sources()]
    finally:
        services.close()


def _admin_id(monkeypatch: pytest.MonkeyPatch, username: str = "c") -> int:
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": PIN)
    assert cli.main(["create-user", username, "--role", "admin"]) == 0
    services = build_services(get_settings())
    try:
        found = services.repo.find_user_by_username(username)
        assert found is not None
        return found[0].id
    finally:
        services.close()


def test_a_folder_imported_from_the_command_line_belongs_to_the_first_admin(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nobody is logged in on the command line; an ownerless source would make "private"
    hide nothing, so it goes to the first admin, as the upgrade does for old sources."""
    from tests.synthetic import write_photo

    admin = _admin_id(monkeypatch)
    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    assert cli.main(["import", str(tmp_path / "pics")]) == 0
    assert _source_owners() == [admin]


def test_folders_imported_before_the_first_admin_exists_go_to_that_admin(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.synthetic import write_photo

    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    assert cli.main(["import", str(tmp_path / "pics")]) == 0
    assert _source_owners() == [None], "no account yet: nobody to give it to"
    admin = _admin_id(monkeypatch)
    assert _source_owners() == [admin]
    _admin_id(monkeypatch, "second")
    assert _source_owners() == [admin], "a later admin takes nothing over"


def test_ml_backfill_reports_missing_models(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["ml-backfill"]) == 0
    out = capsys.readouterr().out
    assert "Queued" in out and "missing" in out


def test_exposure_backfill_queues_one_job_for_the_server_and_no_second_while_it_waits(
    data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["exposure-backfill"]) == 0
    assert "Queued" in capsys.readouterr().out
    assert cli.main(["exposure-backfill"]) == 0
    assert "Already waiting" in capsys.readouterr().out
    services = build_services(get_settings())
    try:
        waiting = [job["kind"] for job in services.repo.list_jobs("queued")]
    finally:
        services.close()
    assert waiting == ["exposure_backfill"], "the command queues; the server's worker runs it"


# --- one command line: every sub-command is listed and reached -------------------------------

SUB_COMMANDS = (
    "import",
    "sources",
    "create-user",
    "set-pin",
    "ml-backfill",
    "exposure-backfill",
    "export-library",
    "verify-library",
    "doctor",
    "backup",
)


def test_help_lists_every_sub_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--help"])
    assert stopped.value.code == 0
    out = capsys.readouterr().out
    listed = out.split("{", 1)[1].split("}", 1)[0].split(",")
    assert tuple(listed) == SUB_COMMANDS
    for name in SUB_COMMANDS:
        assert f"\n    {name}" in out, f"{name} has no line of help"


def test_sources_lists_the_folders_the_library_imports_from(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.synthetic import write_photo

    assert cli.main(["sources"]) == 0
    assert capsys.readouterr().out == ""
    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    assert cli.main(["import", str(tmp_path / "pics"), "--label", "Holiday"]) == 0
    capsys.readouterr()
    assert cli.main(["sources"]) == 0
    assert capsys.readouterr().out == f"  1  enabled   {'Holiday':<24} {tmp_path / 'pics'}\n"


def test_an_unknown_sub_command_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["no-such-command"])
    assert stopped.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


MINIMAL_ARGV = {
    "import": ["import", "folder"],
    "sources": ["sources"],
    "create-user": ["create-user", "name"],
    "set-pin": ["set-pin", "name"],
    "ml-backfill": ["ml-backfill"],
    "exposure-backfill": ["exposure-backfill"],
    "export-library": ["export-library", "destination"],
    "verify-library": ["verify-library"],
    "doctor": ["doctor"],
    "backup": ["backup", "list"],
}


def test_the_command_table_is_exactly_the_documented_sub_commands() -> None:
    assert tuple(command.name for command in cli.COMMANDS) == SUB_COMMANDS
    assert set(MINIMAL_ARGV) == set(SUB_COMMANDS)


@pytest.mark.parametrize("name", SUB_COMMANDS)
def test_the_dispatcher_reaches_each_sub_command(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached: list[str] = []

    def stub(command: Command) -> Command:
        def run(args: object) -> int:
            reached.append(command.name)
            return 7

        return dataclasses.replace(command, run=run)

    monkeypatch.setattr(cli, "COMMANDS", tuple(stub(command) for command in cli.COMMANDS))
    assert cli.main(MINIMAL_ARGV[name]) == 7
    assert reached == [name]
