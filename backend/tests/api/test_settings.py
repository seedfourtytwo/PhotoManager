"""One Settings, read once, with nested sections; every existing env name still works (B22)."""

import os
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings

from photo_assistant.api.settings import IntegrationSettings, MlSettings, OpsSettings, Settings


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
