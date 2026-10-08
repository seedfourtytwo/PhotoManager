"""One Settings, read once, with nested sections; every existing env name still works (B22)."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import (
    IntegrationSettings,
    MlSettings,
    OpsSettings,
    Settings,
    unknown_setting_names,
)


def test_no_setting_leaks_in_from_the_shell_that_started_the_tests() -> None:
    assert [name for name in os.environ if name.startswith("PA_")] == []


def test_the_flat_environment_names_fill_the_nested_sections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = {
        "PA_DATA_ROOT": str(tmp_path),
        "PA_UPLOAD_MAX_MB": "1.5",
        "PA_RCLONE_TPSLIMIT": "2",
        "PA_AI_PROVIDER": "ollama",
        "PA_ML_FACE_MODEL": "yunet_sface",
        "PA_ML_ENABLED": "false",
        "PA_ML_MODELS_DIR": "/models",
        "PA_BACKUP_ENABLED": "false",
        "PA_RESTIC_BINARY": "/opt/restic",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.data_root == tmp_path
    assert (s.integrations.upload_max_mb, s.integrations.rclone_tpslimit) == (1.5, 2.0)
    assert s.integrations.ollama() is not None
    assert (s.ml.face_model, s.ml.enabled, s.ml.models_dir) == (
        "yunet_sface",
        False,
        Path("/models"),
    )
    assert (s.ops.backup_enabled, s.ops.restic_binary) == (False, "/opt/restic")


def test_a_dotenv_file_works_and_the_environment_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("PA_ML_CLIP_BATCH_SIZE=8\nPA_BACKUP_POLL_SECONDS=5\nPA_PORT=9123\n")
    monkeypatch.setenv("PA_BACKUP_POLL_SECONDS", "7")
    s = Settings(_env_file=dotenv)  # type: ignore[call-arg]
    assert s.ml.clip_batch_size == 8
    assert s.ops.backup_poll_seconds == 7.0
    assert s.port == 9123


def test_explicit_values_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PA_UPLOAD_MAX_MB", "1")
    s = Settings(_env_file=None, integrations=IntegrationSettings(upload_max_mb=3))  # type: ignore[call-arg]
    assert s.integrations.upload_max_mb == 3


def test_the_sections_are_plain_models_read_once_through_settings() -> None:
    for section in (IntegrationSettings, MlSettings, OpsSettings):
        assert not issubclass(section, BaseSettings), section
    assert issubclass(Settings, BaseSettings)


@pytest.mark.parametrize(
    "spelling",
    [
        '["127.0.0.1","photos.example.ts.net"]',  # JSON, as in .env and compose's env_file
        "[127.0.0.1,photos.example.ts.net]",  # what systemd's EnvironmentFile leaves of it
        "127.0.0.1, photos.example.ts.net",
    ],
)
def test_allowed_hosts_reads_json_a_quote_stripped_list_and_comma_text(
    monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    monkeypatch.setenv("PA_ALLOWED_HOSTS", spelling)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.allowed_hosts == ["127.0.0.1", "photos.example.ts.net"]


def test_allowed_hosts_still_takes_a_list_and_one_bare_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None, allowed_hosts=["a", "b"]).allowed_hosts == ["a", "b"]  # type: ignore[call-arg]
    monkeypatch.setenv("PA_ALLOWED_HOSTS", "photos.example.ts.net")
    assert Settings(_env_file=None).allowed_hosts == ["photos.example.ts.net"]  # type: ignore[call-arg]


def test_misspelt_setting_names_are_found(monkeypatch: pytest.MonkeyPatch) -> None:
    known = ("PA_PORT", "PA_ALLOWED_HOSTS", "PA_UPLOAD_MAX_MB", "PA_ML_ENABLED", "PA_RESTIC_BINARY")
    for name in (*known, "PA_ALLOWED_HOST", "PA_ML_CLIP_MODLE", "PATH_LIKE", "OTHER"):
        monkeypatch.setenv(name, "1")
    assert unknown_setting_names(os.environ) == ["PA_ALLOWED_HOST", "PA_ML_CLIP_MODLE"]


def test_the_server_warns_at_startup_about_a_setting_name_it_does_not_know(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PA_ALLOWED_HOST", "photos.example.ts.net")
    settings = Settings(_env_file=None, data_root=tmp_path, worker_enabled=False)  # type: ignore[call-arg]
    with TestClient(create_app(settings)):
        pass
    lines = (tmp_path / "logs" / "photo-assistant.log").read_text().splitlines()
    warnings = [json.loads(line) for line in lines if '"WARNING"' in line]
    assert any("PA_ALLOWED_HOST" in w["message"] for w in warnings), lines
