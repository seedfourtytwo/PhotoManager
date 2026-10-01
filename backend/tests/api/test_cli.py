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
