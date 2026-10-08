"""API test helpers: an app per test, logged-in clients for several users."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from photo_assistant.api.main import _domain_error, create_app
from photo_assistant.api.services import Services
from photo_assistant.api.settings import Settings
from photo_assistant.domain.errors import DomainError

BASE = "http://127.0.0.1"
PIN = "1234"


def make_settings(data_root: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "data_root": data_root,
        "worker_enabled": False,
        "min_free_gb": 0,
        "argon2_time_cost": 1,
        "argon2_memory_kib": 64,
    }
    # never the developer's own ~/.config: backup keys made by a test stay in its folder
    values["ops"] = {"backup_key_dir": data_root.parent / "backup-keys"}
    values.update(overrides)
    return Settings(**values)


def answer_domain_errors(app: FastAPI) -> None:
    """For a test that builds its own small app around one router: the routes leave domain
    errors to the app's one handler, so that app needs it as the real one does."""
    app.add_exception_handler(DomainError, _domain_error)


def services_of(client: TestClient) -> Services:
    app: FastAPI = client.app  # type: ignore[assignment]
    s: Services = app.state.services
    return s


def login(app: FastAPI, username: str, pin: str = PIN) -> TestClient:
    """Another browser: a fresh client on the same running app, logged in as ``username``."""
    client = TestClient(app, base_url=BASE)
    response = client.post("/api/auth/login", json={"username": username, "pin": pin})
    assert response.status_code == 200, response.text
    return client


def add_user(admin: TestClient, username: str, role: str = "member") -> TestClient:
    """Create an account through the admin API and return a client logged in as it."""
    created = admin.post(
        "/api/users",
        json={
            "username": username,
            "display_name": username.title(),
            "pin": PIN,
            "role": role,
        },
    )
    assert created.status_code == 201, created.text
    return login(admin.app, username)  # type: ignore[arg-type]


@pytest.fixture
def anon(tmp_path: Path) -> Iterator[TestClient]:
    """A running app with no accounts yet, and a client without a session."""
    with TestClient(create_app(make_settings(tmp_path / "data")), base_url=BASE) as c:
        yield c


@pytest.fixture
def admin(anon: TestClient) -> TestClient:
    """The first-run admin, logged in (the same client as ``anon``, now with a session)."""
    response = anon.post("/api/setup", json={"username": "admin", "display_name": "C", "pin": PIN})
    assert response.status_code == 201, response.text
    return anon


def import_folder(admin: TestClient, folder: Path, label: str) -> int:
    """Register a folder as a source (as the admin), scan it and run every follow-up job."""
    created = admin.post("/api/sources", json={"label": label, "path": str(folder)})
    assert created.status_code == 201, created.text
    source_id: int = created.json()["id"]
    assert admin.post(f"/api/sources/{source_id}/scan").status_code == 202
    services_of(admin).worker.run_until_idle()
    return source_id


def asset_id_of(client: TestClient, source_id: int, relative_path: str) -> int:
    found = services_of(client).repo.asset_id_for_source_path(source_id, relative_path)
    assert found is not None, relative_path
    return found


def refusal(response: Response) -> tuple[int, object]:
    """Status and body of a refused request: both are the contract (the web app shows the
    sentence), so tests compare them whole."""
    return response.status_code, response.json()


def user_id_of(admin: TestClient, username: str) -> int:
    users = admin.get("/api/users").json()
    found: int = next(u["id"] for u in users if u["username"] == username)
    return found
