"""Proton Drive sources over HTTP, against the stand-in CLI: sign-in state, the folder list,
adding a source and pulling it."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.api.deps import admin_user
from photo_assistant.api.integrations import Integrations, build_integrations
from photo_assistant.api.routes import proton, remote_sources
from photo_assistant.api.settings import IntegrationSettings
from tests.api.test_remote_sources_api import ADMIN, StubImporter, _admin_from_header
from tests.proton_cloud import Cloud


@dataclass
class World:
    client: TestClient
    repo: SqliteRepository
    data: Path
    cloud: Cloud
    integrations: Integrations


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.folder("/", {"type": "folder", "uid": "m", "name": "my-files"})
    cloud.folder(
        "/my-files",
        {"type": "folder", "uid": "t", "name": "Trips"},
        {"type": "folder", "uid": "a", "name": "archive"},
    )
    cloud.folder("/my-files/Trips", cloud.image("f1", "peak.jpg"))
    conn = open_database(":memory:")
    repo = SqliteRepository(conn)
    app = FastAPI()
    app.include_router(proton.router)
    app.include_router(remote_sources.router)
    integrations = build_integrations(
        data_root=tmp_path / "data",
        settings=IntegrationSettings(proton_drive_binary=str(cloud.binary)),
        conn=conn,
        repo=repo,
        importer=StubImporter(),
    )
    app.state.integrations = integrations
    app.dependency_overrides[admin_user] = _admin_from_header
    client = TestClient(app, base_url="http://127.0.0.1")
    yield World(client, repo, tmp_path / "data", cloud, integrations)
    conn.close()


def test_status_says_ready_when_signed_in(world: World) -> None:
    assert world.client.get("/api/proton", headers=ADMIN).json() == {
        "ready": True,
        "problem": None,
    }


def test_status_says_how_to_sign_in_when_signed_out(world: World) -> None:
    world.cloud.state["signed_in"] = False
    world.cloud.save()
    body = world.client.get("/api/proton", headers=ADMIN).json()
    assert body["ready"] is False and "proton-drive auth login" in body["problem"]


def test_status_says_when_the_tool_is_missing(world: World, tmp_path: Path) -> None:
    world.integrations.proton._binary = str(tmp_path / "none")
    body = world.client.get("/api/proton", headers=ADMIN).json()
    assert body["ready"] is False and "not installed" in body["problem"]


def test_folders_of_a_place_are_listed_for_the_picker(world: World) -> None:
    response = world.client.get("/api/proton/folders?path=/my-files", headers=ADMIN)
    assert response.json() == {"path": "/my-files", "folders": ["archive", "Trips"]}


@pytest.mark.parametrize(
    ("path", "code"), [("/my-files/Nope", 404), ("/trash", 422), ("/photos", 422)]
)
def test_folders_refuses_places_that_cannot_be_browsed(world: World, path: str, code: int) -> None:
    response = world.client.get("/api/proton/folders", params={"path": path}, headers=ADMIN)
    assert response.status_code == code


@pytest.mark.parametrize("path", ["/photos", "/my-files", "/my-files/Trips"])
def test_a_proton_source_is_added_with_a_staging_folder(world: World, path: str) -> None:
    response = world.client.post(
        "/api/proton/sources", json={"label": "Proton", "path": path}, headers=ADMIN
    )
    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "label": "Proton", "path": path}
    source = world.repo.get_source(body["id"])
    assert source is not None
    assert (source.kind, source.root) == ("proton", str(world.data / "staging" / str(source.id)))


@pytest.mark.parametrize(("path", "code"), [("/my-files/Nope", 404), ("/trash", 422), ("", 422)])
def test_a_source_for_a_missing_or_forbidden_place_is_refused(
    world: World, path: str, code: int
) -> None:
    response = world.client.post(
        "/api/proton/sources", json={"label": "x", "path": path}, headers=ADMIN
    )
    assert response.status_code == code
    assert world.repo.list_sources() == []


def test_nothing_is_added_while_signed_out(world: World) -> None:
    world.cloud.state["signed_in"] = False
    world.cloud.save()
    response = world.client.post(
        "/api/proton/sources", json={"label": "x", "path": "/photos"}, headers=ADMIN
    )
    assert response.status_code == 503
    assert "proton-drive auth login" in response.json()["detail"]
    assert world.client.get("/api/proton/folders?path=/my-files", headers=ADMIN).status_code == 503


def test_a_proton_source_is_pulled_like_any_remote_source(world: World) -> None:
    created = world.client.post(
        "/api/proton/sources", json={"label": "Trips", "path": "/my-files/Trips"}, headers=ADMIN
    ).json()
    queued = world.client.post(f"/api/remote-sources/{created['id']}/pull", headers=ADMIN)
    assert queued.status_code == 202
    outcome = world.integrations.sync_source.run(created["id"])
    assert outcome.sync is not None and outcome.sync.copied == 1
    staging = world.data / "staging" / str(created["id"])
    assert [p.name for p in staging.iterdir()] == ["peak.jpg"]
    verbs = {tuple(call[:2]) for call in world.cloud.calls()}
    assert verbs == {("filesystem", "list"), ("filesystem", "download")}


def test_proton_needs_a_session(world: World) -> None:
    assert world.client.get("/api/proton").status_code == 401


def test_the_stored_settings_hold_no_account_details(world: World) -> None:
    created = world.client.post(
        "/api/proton/sources", json={"label": "P", "path": "/photos"}, headers=ADMIN
    ).json()
    config = world.integrations.remote_sources.remote_config(created["id"])
    assert config is not None
    assert json.dumps(config.to_mapping()) == '{"provider": "proton", "path": "/photos"}'
