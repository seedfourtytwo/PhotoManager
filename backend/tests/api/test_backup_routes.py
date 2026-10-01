"""Backup admin endpoints, with the real store and restic and the real job queue."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.api.ops_services import OpsServices, build_ops_services
from photo_assistant.api.ops_settings import OpsSettings
from photo_assistant.api.routes import backup

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing"),
]


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "data"
        self.root.mkdir()
        self.repo = SqliteRepository(open_database(self.root / "library.db"))
        self.ops: OpsServices = build_ops_services(
            self.root, OpsSettings(restic_cache_dir=tmp_path / "cache"), queue=self.repo
        )
        self.password = tmp_path / "secret" / "pw"
        self.password.parent.mkdir()
        self.password.write_text("pw\n")
        self.disk = tmp_path / "disk"
        self.disk.mkdir()
        app = FastAPI()
        app.state.ops = self.ops
        app.include_router(backup.router)
        self.client = TestClient(app)

    def work(self) -> None:
        """What the worker does with queued backup jobs."""
        handlers = self.ops.backup.job_handlers()
        while job := self.repo.claim_next_job(self.ops.backup._clock.now()):
            handlers[job.kind](job.payload)
            self.repo.complete_job(job.id)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path)
    yield e
    e.ops.close()
    e.repo.close()


def _add(env: Env, **extra: object) -> dict[str, object]:
    body = {
        "label": "Disk",
        "repository": str(env.disk / "photos"),
        "password_file": str(env.password),
    } | extra
    response = env.client.post("/api/backups", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_add_run_and_watch_a_backup(env: Env) -> None:
    assert env.client.get("/api/backups").json() == []
    target = _add(env, schedule="weekly sun 03:00", retention={"daily": 3})
    assert target["retention"] == {"daily": 3, "weekly": 4, "monthly": 12}
    assert target["next_run_at"] and not target["needs_attention"] and target["kind"] == "local"
    queued = env.client.post(f"/api/backups/{target['id']}/run")
    assert queued.status_code == 202 and queued.json()["target_id"] == target["id"]
    env.client.post(f"/api/backups/{target['id']}/restore-test")
    env.work()
    runs = env.client.get(f"/api/backups/{target['id']}/runs").json()
    assert [(r["kind"], r["status"]) for r in runs] == [
        ("restore_test", "succeeded"),
        ("backup", "succeeded"),
    ]
    (listed,) = env.client.get("/api/backups").json()
    assert listed["last_success_at"] and listed["repo_bytes"]
    assert listed["last_run"]["snapshot_id"]
    assert env.client.get(f"/api/backups/{target['id']}/runs?limit=1").json()[0]["kind"] == (
        "restore_test"
    )


def test_failures_show_up_in_status(env: Env) -> None:
    target = _add(env, repository="/media/nobody/NoDisk/photos")
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    (listed,) = env.client.get("/api/backups").json()
    assert listed["needs_attention"] and "plug in" in listed["last_run"]["error"]
    patched = env.client.patch(f"/api/backups/{target['id']}", json={"enabled": False})
    assert patched.json()["enabled"] is False and not patched.json()["needs_attention"]


def test_validation_and_unknown_targets(env: Env) -> None:
    _add(env)
    again = env.client.post(
        "/api/backups",
        json={"label": "Disk", "repository": "/x", "password_file": str(env.password)},
    )
    assert again.status_code == 409
    bad = env.client.post(
        "/api/backups",
        json={
            "label": "B",
            "repository": "/x",
            "password_file": str(env.password),
            "schedule": "sometimes",
        },
    )
    assert bad.status_code == 422 and "schedule" in bad.json()["detail"]
    inside = env.client.post(
        "/api/backups",
        json={"label": "C", "repository": str(env.root / "b"), "password_file": str(env.password)},
    )
    assert inside.status_code == 422
    for method, path in (
        ("post", "/api/backups/99/run"),
        ("post", "/api/backups/99/restore-test"),
        ("get", "/api/backups/99/runs"),
    ):
        assert getattr(env.client, method)(path).status_code == 404
    assert env.client.patch("/api/backups/99", json={"enabled": True}).status_code == 404


def test_status_lookup_for_a_vanished_target(env: Env) -> None:
    with pytest.raises(backup.HTTPException):
        backup._status_of(env.ops.backup, 12345)
