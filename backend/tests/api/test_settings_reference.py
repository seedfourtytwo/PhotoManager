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


def test_a_setting_without_a_meaning_stops_the_script(monkeypatch: pytest.MonkeyPatch) -> None:
    meanings = dict(ref.MEANINGS)
    del meanings["PA_WORKER_ENABLED"]
    monkeypatch.setattr(ref, "MEANINGS", meanings)
    with pytest.raises(SystemExit, match="PA_WORKER_ENABLED"):
        ref.rows()


def test_a_meaning_for_a_setting_that_is_gone_stops_the_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ref, "MEANINGS", ref.MEANINGS | {"PA_REMOVED_LONG_AGO": "…"})
    with pytest.raises(SystemExit, match="PA_REMOVED_LONG_AGO"):
        ref.rows()


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
