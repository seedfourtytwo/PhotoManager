"""docs/guides/settings.md is generated from ``Settings`` and must never fall behind it."""

from pathlib import Path

import pytest
from pydantic import BaseModel
from scripts import settings_reference as ref

from photo_assistant.api.settings import IntegrationSettings, MlSettings, OpsSettings, Settings


def _env_names() -> set[str]:
    """Every variable ``Settings`` reads, worked out here without the script's help."""
    top = {
        f"PA_{name}".upper()
        for name, field in Settings.model_fields.items()
        if not (isinstance(field.annotation, type) and issubclass(field.annotation, BaseModel))
    }
    flat = {*IntegrationSettings.model_fields, *OpsSettings.model_fields}
    ml = {f"PA_ML_{name}".upper() for name in MlSettings.model_fields}
    return top | {f"PA_{name}".upper() for name in flat} | ml


def test_every_setting_has_exactly_one_row() -> None:
    names = [row.name for row in ref.rows()]
    assert sorted(names) == sorted(_env_names())
    assert all(row.meaning.strip() for row in ref.rows())


def test_the_committed_reference_is_up_to_date() -> None:
    committed = ref.TARGET.read_text(encoding="utf-8")
    assert committed == ref.render(), (
        "docs/guides/settings.md is out of date: "
        "run `uv run python scripts/settings_reference.py` in backend/"
    )


def test_defaults_are_written_the_same_on_every_machine() -> None:
    text = ref.render()
    assert str(Path.home()) not in text
    assert "| `PA_DATA_ROOT` | `~/PhotoAssistant/data` |" in text
    assert "| `PA_ALLOWED_HOSTS` | `127.0.0.1,localhost` |" in text
    assert "| `PA_RCLONE_CONFIG` | not set |" in text
    assert "| `PA_BACKUP_ENABLED` | `true` |" in text


def test_a_setting_without_a_description_stops_the_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for model, field, name in (
        (Settings, "worker_enabled", "PA_WORKER_ENABLED"),
        (MlSettings, "clip_model", "PA_ML_CLIP_MODEL"),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(model.model_fields[field], "description", None)
            with pytest.raises(SystemExit, match=name):
                ref.rows()
    with monkeypatch.context() as patch:
        patch.setattr(OpsSettings.model_fields["restic_binary"], "description", "  ")
        with pytest.raises(SystemExit, match="PA_RESTIC_BINARY"):
            ref.rows()


def test_the_meanings_live_on_the_fields_themselves() -> None:
    """One place per setting: its type, its default and what it does."""
    assert not hasattr(ref, "MEANINGS")
    described = Settings.model_fields["port"].description
    assert described == "Port the server listens on."
    assert f"| `PA_PORT` | `8420` | {described} |" in ref.render()


def test_check_mode_reports_a_stale_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = tmp_path / "settings.md"
    stale.write_text("old\n")
    monkeypatch.setattr(ref, "TARGET", stale)
    assert ref.main(["--check"]) == 1
    assert stale.read_text() == "old\n", "--check never writes"
    assert ref.main([]) == 0
    assert stale.read_text(encoding="utf-8") == ref.render()
    assert ref.main(["--check"]) == 0
    capsys.readouterr()
