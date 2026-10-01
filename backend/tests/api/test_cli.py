"""Headless bootstrap: create the first admin from the command line."""

from pathlib import Path

import pytest

from photo_assistant import __main__ as cli
from photo_assistant.api.settings import get_settings
from photo_assistant.domain.access import Role

PASSWORD = "a long enough password"


@pytest.fixture
def data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    get_settings.cache_clear()
    monkeypatch.setenv("PA_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("PA_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("PA_ARGON2_MEMORY_KIB", "64")
    yield tmp_path / "data"
    get_settings.cache_clear()


def test_create_user_prompts_for_the_password_twice(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c", "--role", "admin"]) == 0
    assert "Created admin 'c'" in capsys.readouterr().out
    services = cli.build_services(get_settings())
    try:
        found = services.repo.find_user_by_username("c")
        assert found is not None and found[0].role is Role.ADMIN
    finally:
        services.close()


def test_create_user_refuses_mismatched_or_short_passwords(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PASSWORD, "something else entirely", "short", "short"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "c"]) == 2
    assert "do not match" in capsys.readouterr().err
    assert cli.main(["create-user", "c"]) == 2
    assert "10 characters" in capsys.readouterr().err


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
