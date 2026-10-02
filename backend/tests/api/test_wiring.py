"""The merged app wired end to end: every branch's services behind core's real auth.

Each test runs the real ``create_app`` (composition root, routers, session cookies), so these
check the wiring itself rather than the features (the branches test those on their own).
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import IntegrationSettings
from tests.api.conftest import (
    BASE,
    PASSWORD,
    add_user,
    import_folder,
    make_settings,
    services_of,
    user_id_of,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "photos"
JPEG = (FIXTURES / "IMG_1002.JPG").read_bytes()


def _upload(client: TestClient, name: str = "IMG_1002.JPG", **kw: object) -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/api/upload",
        files=[("file", (name, JPEG, "image/jpeg"))],
        **kw,  # type: ignore[arg-type]
    )
    assert response.status_code == 200, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


# --- composition ------------------------------------------------------------------------------


def test_the_worker_handles_every_job_kind_of_every_branch(admin: TestClient) -> None:
    kinds = services_of(admin).worker.kinds
    core = {"scan_source", "preview", "geocode", "group", "purge_trash"}
    ml = {"embed_clip", "detect_faces", "cluster_faces", "auto_tag"}
    ops = {"backup_run", "backup_restore_test"}
    assert core | ml | ops <= kinds


def test_housekeeping_runs_backups_trash_purge_and_nightly_face_clustering(
    admin: TestClient,
) -> None:
    periodic = services_of(admin).ops.periodic
    assert periodic.task_names == [
        "due backups",
        "trash purge",
        "cluster faces",
        "optimize database",
    ]


def test_housekeeping_queues_the_purge_and_a_global_face_clustering(admin: TestClient) -> None:
    services = services_of(admin)
    services.ops.periodic.tick()
    queued = {(j["kind"], str(j["payload"])) for j in services.repo.list_jobs()}
    assert ("purge_trash", "{}") in queued
    assert ("cluster_faces", "{}") in queued


def test_an_m1_library_boots_and_its_sources_go_to_the_first_admin(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    from tests.adapters.test_migrations import _make_v3_library

    _make_v3_library(data / "library.db")
    with TestClient(create_app(make_settings(data)), base_url=BASE) as client:
        created = client.post(
            "/api/setup", json={"username": "c", "display_name": "C", "password": PASSWORD}
        )
        assert created.status_code == 201
        assert [s["owner_id"] for s in client.get("/api/sources").json()] == [created.json()["id"]]
        assert client.get("/api/assets").json()["items"][0]["id"] in (1, 2)
    assert list((data / "db-backups").glob("library-v3-*.db"))


# --- upload: session or device token, into a private inbox ------------------------------------


def test_upload_works_with_the_session_cookie(admin: TestClient) -> None:
    body = _upload(admin)
    assert body["files"][0]["outcome"] == "stored"
    assert body["import_job_id"] is not None


def test_upload_needs_a_login(anon: TestClient) -> None:
    response = anon.post("/api/upload", files=[("file", ("a.jpg", JPEG, "image/jpeg"))])
    assert response.status_code == 401


def test_guests_cannot_upload(admin: TestClient) -> None:
    guest = add_user(admin, "gina", role="guest")
    response = guest.post("/api/upload", files=[("file", ("a.jpg", JPEG, "image/jpeg"))])
    assert response.status_code == 403


def test_an_uploaded_photo_is_private_to_the_uploader(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    max_ = add_user(admin, "max")
    _upload(lea)
    services_of(admin).worker.run_until_idle()

    assert len(lea.get("/api/assets").json()["items"]) == 1
    assert max_.get("/api/assets").json()["items"] == []
    (inbox,) = [s for s in lea.get("/api/sources").json() if s["kind"] == "inbox"]
    assert inbox["owner_id"] == user_id_of(admin, "lea")
    assert lea.get(f"/api/sources/{inbox['id']}/access").status_code == 403, "admin-only"
    assert admin.get(f"/api/sources/{inbox['id']}/access").json() == {
        "everyone": None,
        "users": [{"user_id": user_id_of(admin, "lea"), "level": "edit"}],
    }
    assert all(s["kind"] != "inbox" for s in max_.get("/api/sources").json())


def test_a_device_token_uploads_without_a_session(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    created = lea.post("/api/devices", json={"name": "iPhone", "platform": "ios"})
    assert created.status_code == 201
    token = created.json()["token"]

    phone = TestClient(admin.app, base_url=BASE)
    body = _upload(phone, headers={"Authorization": f"Bearer {token}"})
    assert body["files"][0]["outcome"] == "stored"
    services_of(admin).worker.run_until_idle()
    assert len(lea.get("/api/assets").json()["items"]) == 1


def test_a_disabled_accounts_device_token_stops_working(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    token = lea.post("/api/devices", json={"name": "iPhone"}).json()["token"]
    admin.patch(f"/api/users/{user_id_of(admin, 'lea')}", json={"disabled": True})

    phone = TestClient(admin.app, base_url=BASE)
    response = phone.post(
        "/api/upload",
        files=[("file", ("a.jpg", JPEG, "image/jpeg"))],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_devices_need_a_session(anon: TestClient) -> None:
    assert anon.get("/api/devices").status_code == 401


# --- admin-only areas use core's admin check -------------------------------------------------


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")
def test_remote_sources_are_admin_only_and_open_to_everyone_once_added(tmp_path: Path) -> None:
    config = tmp_path / "rclone.conf"
    config.write_text("[mega]\ntype = local\n")
    settings = make_settings(
        tmp_path / "data", integrations=IntegrationSettings(rclone_config=config)
    )
    with TestClient(create_app(settings), base_url=BASE) as admin:
        admin.post("/api/setup", json={"username": "c", "display_name": "C", "password": PASSWORD})
        lea = add_user(admin, "lea")
        assert lea.get("/api/remote-sources/remotes").status_code == 403
        assert admin.get("/api/remote-sources/remotes").json() == {"remotes": ["mega"]}
        added = admin.post(
            "/api/remote-sources", json={"label": "MEGA", "remote": "mega", "path": "x"}
        )
        assert added.status_code == 201
        source_id = added.json()["id"]
        assert lea.post(f"/api/remote-sources/{source_id}/pull").status_code == 403
        assert any(s["id"] == source_id for s in lea.get("/api/sources").json())


def test_backups_are_admin_only(admin: TestClient, anon_second: TestClient) -> None:
    lea = add_user(admin, "lea")
    assert admin.get("/api/backups").status_code == 200
    assert lea.get("/api/backups").status_code == 403
    assert anon_second.get("/api/backups").status_code == 401


@pytest.fixture
def anon_second(admin: TestClient) -> TestClient:
    """A browser without a session on the same running app."""
    return TestClient(admin.app, base_url=BASE)


def test_import_then_everything_downstream_runs(admin: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "pics"
    folder.mkdir()
    shutil.copy(FIXTURES / "IMG_1002.JPG", folder / "a.jpg")
    import_folder(admin, folder, "Pics")
    jobs = services_of(admin).repo.list_jobs()
    assert {j["kind"] for j in jobs} >= {"scan_source", "preview", "embed_clip", "detect_faces"}
    assert all(j["status"] == "done" for j in jobs), jobs


def test_due_backups_are_queued_for_the_long_lane_not_run_inline(admin: TestClient) -> None:
    """B24: the periodic thread only enqueues; the long-job lane runs the backups."""
    services = services_of(admin)
    services.ops.periodic.tick()
    queued = {j["kind"] for j in services.repo.list_jobs()}
    assert "backup_due" in queued
    assert {"backup_run", "backup_restore_test", "backup_due", "scan_source"} <= (
        services.worker.long_kinds
    )
