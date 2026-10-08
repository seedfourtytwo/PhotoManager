"""Registering and pulling remote (rclone) sources over HTTP, with a local rclone remote."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.api.deps import admin_user
from photo_assistant.api.integrations import build_integrations
from photo_assistant.api.routes import remote_sources
from photo_assistant.api.settings import IntegrationSettings
from photo_assistant.domain.access import Role, User
from photo_assistant.domain.model import ImportReport, RunStatus

pytestmark = pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")
ADMIN = {"X-Test-User": "1"}


class StubImporter:
    def run(self, source_id: int) -> tuple[int, ImportReport]:
        return 1, ImportReport(source_id, RunStatus.DONE)


@dataclass
class World:
    client: TestClient
    repo: SqliteRepository
    data: Path


def _admin_from_header(request: Request) -> User:
    """Stands in for core's admin check (session + role; covered in test_wiring.py)."""
    user = request.headers.get("x-test-user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "log in first")
    return User(int(user), "admin", "Admin", Role.ADMIN)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    config = tmp_path / "rclone.conf"
    config.write_text("[mega]\ntype = local\n")
    conn = open_database(":memory:")
    repo = SqliteRepository(conn)
    app = FastAPI()
    app.include_router(remote_sources.router)
    integrations = build_integrations(
        data_root=tmp_path / "data",
        settings=IntegrationSettings(rclone_config=config),
        conn=conn,
        repo=repo,
        importer=StubImporter(),
    )
    app.state.services = SimpleNamespace(integrations=integrations)
    app.dependency_overrides[admin_user] = _admin_from_header
    yield World(TestClient(app, base_url="http://127.0.0.1"), repo, tmp_path / "data")
    conn.close()


def test_the_configured_rclone_remotes_are_listed(world: World) -> None:
    response = world.client.get("/api/remote-sources/remotes", headers=ADMIN)
    assert response.json() == {"remotes": ["mega"]}


def test_a_remote_source_is_registered_with_a_staging_folder(world: World) -> None:
    response = world.client.post(
        "/api/remote-sources",
        json={"label": "MEGA camera", "remote": "mega", "path": "Camera Uploads"},
        headers=ADMIN,
    )
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "label": "MEGA camera",
        "remote": "mega",
        "path": "Camera Uploads",
    }
    source = world.repo.get_source(body["id"])
    assert source is not None
    assert (source.kind, source.root) == ("rclone", str(world.data / "staging" / str(source.id)))


@pytest.mark.parametrize("remote", ["megaa", "-x", ":local:"])
def test_unknown_or_unsafe_remotes_are_422(world: World, remote: str) -> None:
    response = world.client.post(
        "/api/remote-sources", json={"label": "x", "remote": remote}, headers=ADMIN
    )
    assert response.status_code == 422


def test_pull_queues_a_scan_job_for_remote_sources_only(world: World) -> None:
    created = world.client.post(
        "/api/remote-sources", json={"label": "M", "remote": "mega"}, headers=ADMIN
    ).json()
    response = world.client.post(f"/api/remote-sources/{created['id']}/pull", headers=ADMIN)
    assert response.status_code == 202
    (job,) = world.repo.list_jobs()
    assert (job["kind"], job["payload"]) == ("scan_source", {"source_id": created["id"]})
    folder = world.repo.add_source("Pictures", "/pictures")
    missing = world.client.post(f"/api/remote-sources/{folder.id}/pull", headers=ADMIN)
    assert missing.status_code == 404


def test_rclone_missing_is_a_clear_503(world: World, tmp_path: Path) -> None:
    world.client.app.state.services.integrations.rclone._binary = str(tmp_path / "none")  # type: ignore[attr-defined]
    response = world.client.get("/api/remote-sources/remotes", headers=ADMIN)
    assert response.status_code == 503
    assert "rclone is not installed" in response.json()["detail"]


def test_remote_sources_need_a_session(world: World) -> None:
    assert world.client.get("/api/remote-sources/remotes").status_code == 401


def test_ai_stays_off_unless_ollama_is_chosen(tmp_path: Path) -> None:
    from photo_assistant.adapters.null_ai import NullAIProvider
    from photo_assistant.adapters.ollama_ai import OllamaProvider

    conn = open_database(":memory:")
    common = {"data_root": tmp_path, "conn": conn, "repo": SqliteRepository(conn)}
    off = build_integrations(settings=IntegrationSettings(), importer=StubImporter(), **common)  # type: ignore[arg-type]
    on = build_integrations(
        settings=IntegrationSettings(ai_provider="ollama", ollama_plan_model="p"),
        importer=StubImporter(),
        **common,  # type: ignore[arg-type]
    )
    assert isinstance(off.ai, NullAIProvider)
    assert isinstance(on.ai, OllamaProvider)
    conn.close()


def test_the_importer_store_accepts_staging_and_inbox_folders(tmp_path: Path) -> None:
    from photo_assistant.adapters.filesystem import DiskLibraryStore
    from photo_assistant.api.integrations import with_source_areas

    store = with_source_areas(DiskLibraryStore(tmp_path), tmp_path)
    assert not store.overlaps(tmp_path / "staging" / "3")
    assert not store.overlaps(tmp_path / "inbox" / "1")
    assert store.overlaps(tmp_path / "originals")
