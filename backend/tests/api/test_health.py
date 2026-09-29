from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant import __version__
from photo_assistant.api.main import create_app
from photo_assistant.api.settings import Settings, get_settings


def test_health_reports_ok_and_version(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_data_root_comes_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PA_DATA_ROOT", str(tmp_path))
    assert Settings().data_root == tmp_path


def test_default_app_uses_cached_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("PA_DATA_ROOT", str(tmp_path))
    app = create_app()
    assert app.state.settings.data_root == tmp_path
    assert get_settings() is app.state.settings
    get_settings.cache_clear()
