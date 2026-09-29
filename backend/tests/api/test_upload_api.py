"""Upload, hash check and device-token routes through FastAPI (streamed multipart parsing).

Sessions belong to the core auth work; here a test hook maps an ``X-Test-User`` header to a
user id, exactly where the real session lookup will plug in (docs/wiring/ai-sources.md).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from photo_assistant.adapters.filesystem import Blake3Hasher
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.api.integration_settings import IntegrationSettings
from photo_assistant.api.integrations import Integrations, build_integrations
from photo_assistant.api.routes import upload as upload_routes
from photo_assistant.domain.model import ImportReport, RunStatus
from tests.factories import NOW, new_asset

FIXTURES = Path(__file__).parent.parent / "fixtures" / "photos"
JPEG = (FIXTURES / "IMG_1002.JPG").read_bytes()
PNG = (FIXTURES / "grey-1x1.png").read_bytes()
MONTH = "2026-09"


class FixedClock:
    def now(self) -> datetime:
        return NOW


class StubImporter:
    def run(self, source_id: int) -> tuple[int, ImportReport]:
        return 1, ImportReport(source_id, RunStatus.DONE)


def _session_hook(request: Request) -> int | None:
    user = request.headers.get("x-test-user")
    return int(user) if user else None


@dataclass
class World:
    client: TestClient
    repo: SqliteRepository
    integrations: Integrations
    data: Path


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    data = tmp_path / "data"
    conn = open_database(tmp_path / "library.db")
    repo = SqliteRepository(conn)
    integrations = build_integrations(
        data_root=data,
        settings=IntegrationSettings(upload_max_mb=0.01),
        conn=conn,
        repo=repo,
        importer=StubImporter(),
        clock=FixedClock(),
    )
    app = FastAPI()
    app.include_router(upload_routes.router)
    app.state.integrations = integrations
    app.state.session_user_hook = _session_hook
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield World(client, repo, integrations, data)
    conn.close()


def _as(user: int) -> dict[str, str]:
    return {"X-Test-User": str(user)}


def _upload(world: World, files: list[tuple[str, bytes]], headers: dict[str, str]) -> dict:  # type: ignore[type-arg]
    parts = [("file", (name, content, "application/octet-stream")) for name, content in files]
    response = world.client.post("/api/upload", files=parts, headers=headers)
    assert response.status_code == 200, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


def _inbox_files(world: World, user: int) -> set[str]:
    root = world.data / "inbox" / str(user)
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


# --- upload ----------------------------------------------------------------------------------


def test_upload_stores_photos_in_the_inbox_and_queues_an_import(world: World) -> None:
    body = _upload(world, [("IMG_1002.JPG", JPEG), ("beach day 🌊.png", PNG)], _as(1))
    assert [f["outcome"] for f in body["files"]] == ["stored", "stored"]
    assert body["files"][0]["content_hash"] == Blake3Hasher().hash_file(FIXTURES / "IMG_1002.JPG")
    assert _inbox_files(world, 1) == {f"{MONTH}/IMG_1002.JPG", f"{MONTH}/beach day 🌊.png"}
    (job,) = world.repo.list_jobs()
    assert job["id"] == body["import_job_id"]
    inbox = world.repo.get_source(job["payload"]["source_id"])  # type: ignore[index, call-overload]
    assert inbox is not None
    assert (inbox.kind, inbox.root) == ("inbox", str(world.data / "inbox" / "1"))
    assert list((world.data / "tmp").iterdir()) == []


def test_each_user_has_a_separate_inbox(world: World) -> None:
    _upload(world, [("a.jpg", JPEG)], _as(1))
    _upload(world, [("b.jpg", PNG)], _as(2))
    assert _inbox_files(world, 1) == {f"{MONTH}/a.jpg"}
    assert _inbox_files(world, 2) == {f"{MONTH}/b.jpg"}


def test_the_same_name_twice_gets_a_number(world: World) -> None:
    _upload(world, [("IMG_1.JPG", JPEG), ("IMG_1.JPG", PNG)], _as(1))
    assert _inbox_files(world, 1) == {f"{MONTH}/IMG_1.JPG", f"{MONTH}/IMG_1 (2).JPG"}


@pytest.mark.parametrize(
    ("client_name", "stored"),
    [
        ("../../../etc/evil.jpg", "evil.jpg"),
        ("..\\..\\evil.jpg", "evil.jpg"),
        ("/tmp/abs.jpg", "abs.jpg"),
        ("..", "upload.jpg"),
        (".bashrc", "bashrc.jpg"),
    ],
)
def test_path_traversal_in_file_names_is_neutralised(
    world: World, client_name: str, stored: str
) -> None:
    body = _upload(world, [(client_name, JPEG)], _as(1))
    assert body["files"][0]["stored_as"] == f"{MONTH}/{stored}"
    assert _inbox_files(world, 1) == {f"{MONTH}/{stored}"}
    written = {
        p for p in world.data.parent.rglob("*") if p.is_file() and "library.db" not in p.name
    }
    assert written == {world.data / "inbox" / "1" / MONTH / stored}


def test_non_photos_are_rejected_by_their_bytes(world: World) -> None:
    body = _upload(world, [("holiday.jpg", b"MZ\x90\x00 an executable"), ("ok.jpg", JPEG)], _as(1))
    rejected, stored = body["files"]
    assert rejected["outcome"] == "rejected"
    assert "not a photo" in rejected["reason"]
    assert stored["outcome"] == "stored"
    assert _inbox_files(world, 1) == {f"{MONTH}/ok.jpg"}


def test_files_over_the_size_limit_are_rejected_without_leftovers(world: World) -> None:
    big = JPEG + b"\x00" * 20_000
    body = _upload(world, [("big.jpg", big), ("small.jpg", JPEG)], _as(1))
    assert [f["outcome"] for f in body["files"]] == ["rejected", "stored"]
    assert "limit" in body["files"][0]["reason"]
    assert list((world.data / "tmp").iterdir()) == []


def test_photos_already_in_the_library_are_skipped(world: World) -> None:
    digest = Blake3Hasher().hash_file(FIXTURES / "IMG_1002.JPG")
    asset_id = world.repo.add_asset(new_asset(content_hash=digest), NOW)
    body = _upload(world, [("again.jpg", JPEG)], _as(1))
    assert body["files"][0] | {"outcome": "duplicate", "asset_id": asset_id} == body["files"][0]
    assert body["import_job_id"] is None
    assert not (world.data / "inbox").exists()


def test_form_fields_without_a_file_are_ignored(world: World) -> None:
    response = world.client.post(
        "/api/upload",
        data={"note": "hello"},
        files=[("file", ("a.jpg", JPEG, "image/jpeg"))],
        headers=_as(1),
    )
    assert [f["outcome"] for f in response.json()["files"]] == ["stored"]


def test_a_file_part_without_a_plain_filename_still_counts(world: World) -> None:
    boundary = "b0undary"
    body = (
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=\"file\"; filename*=UTF-8''caf%C3%A9.jpg\r\n"
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode() + JPEG + f"\r\n--{boundary}--\r\n".encode()
    response = world.client.post(
        "/api/upload",
        content=body,
        headers={**_as(1), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.json()["files"][0]["stored_as"] == f"{MONTH}/upload.jpg"


def test_not_multipart_is_refused(world: World) -> None:
    response = world.client.post("/api/upload", content=JPEG, headers=_as(1))
    assert response.status_code == 415


def test_broken_multipart_is_a_bad_request_and_leaves_nothing(world: World) -> None:
    body = b"--x\r\nContent-Disposition: form-data; name=\"f\"; filename=\"a.jpg\"\r\n\r\n" + JPEG
    response = world.client.post(
        "/api/upload",
        content=body + b"garbage-without-closing-boundary\r\n--y--",
        headers={**_as(1), "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 400
    assert not (world.data / "inbox").exists()
    assert list((world.data / "tmp").glob("*")) == []


def test_too_many_files_in_one_request_are_rejected(world: World) -> None:
    world.integrations.upload_max_files = 1
    body = _upload(world, [("a.jpg", JPEG), ("b.jpg", PNG)], _as(1))
    assert [f["outcome"] for f in body["files"]] == ["stored", "rejected"]


# --- check -----------------------------------------------------------------------------------


def test_check_returns_only_the_hashes_the_library_lacks(world: World) -> None:
    known = Blake3Hasher().hash_file(FIXTURES / "IMG_1002.JPG")
    world.repo.add_asset(new_asset(content_hash=known), NOW)
    unknown = "f" * 64
    response = world.client.post(
        "/api/upload/check", json={"hashes": [known, unknown]}, headers=_as(1)
    )
    assert response.status_code == 200
    assert response.json() == {"missing": [unknown]}


def test_check_refuses_malformed_hashes(world: World) -> None:
    response = world.client.post("/api/upload/check", json={"hashes": ["zz"]}, headers=_as(1))
    assert response.status_code == 422


# --- authentication and device tokens --------------------------------------------------------


def _new_token(world: World, user: int = 1, name: str = "C's iPhone") -> tuple[int, str]:
    response = world.client.post(
        "/api/devices", json={"name": name, "platform": "ios"}, headers=_as(user)
    )
    assert response.status_code == 201
    body = response.json()
    return body["device"]["id"], body["token"]


def test_no_session_and_no_token_is_401(world: World) -> None:
    response = world.client.post("/api/upload", files=[("file", ("a.jpg", JPEG))])
    assert response.status_code == 401
    assert world.client.post("/api/upload/check", json={"hashes": []}).status_code == 401
    assert world.client.get("/api/devices").status_code == 401


def test_a_device_token_uploads_into_its_owners_inbox(world: World) -> None:
    _, token = _new_token(world, user=4)
    body = _upload(world, [("IMG_1.HEIC", JPEG)], {"Authorization": f"Bearer {token}"})
    assert body["files"][0]["outcome"] == "stored"
    assert _inbox_files(world, 4) == {f"{MONTH}/IMG_1.HEIC"}


def test_a_wrong_or_revoked_token_is_401_even_with_a_session(world: World) -> None:
    device_id, token = _new_token(world)
    bearer = {"Authorization": f"Bearer {token}"}
    assert world.client.delete(f"/api/devices/{device_id}", headers=_as(1)).status_code == 204
    files = [("file", ("a.jpg", JPEG))]
    assert world.client.post("/api/upload", files=files, headers=bearer).status_code == 401
    wrong = {"Authorization": "Bearer pa_dev_nope", **_as(1)}
    assert world.client.post("/api/upload", files=files, headers=wrong).status_code == 401
    basic = {"Authorization": "Basic dXNlcjpwYXNz"}
    assert world.client.post("/api/upload", files=files, headers=basic).status_code == 401


def test_devices_are_listed_without_their_tokens(world: World) -> None:
    device_id, token = _new_token(world)
    listed = world.client.get("/api/devices", headers=_as(1)).json()
    assert [d["id"] for d in listed] == [device_id]
    assert token not in str(listed)
    assert listed[0]["name"] == "C's iPhone" and listed[0]["revoked"] is False
    assert world.client.get("/api/devices", headers=_as(2)).json() == []


def test_device_tokens_cannot_manage_devices(world: World) -> None:
    _, token = _new_token(world)
    bearer = {"Authorization": f"Bearer {token}"}
    assert world.client.get("/api/devices", headers=bearer).status_code == 401
    response = world.client.post("/api/devices", json={"name": "x"}, headers=bearer)
    assert response.status_code == 401


def test_you_cannot_revoke_someone_elses_device(world: World) -> None:
    device_id, _ = _new_token(world, user=1)
    assert world.client.delete(f"/api/devices/{device_id}", headers=_as(2)).status_code == 404


def test_bad_device_names_are_422(world: World) -> None:
    response = world.client.post(
        "/api/devices", json={"name": "", "platform": "ios"}, headers=_as(1)
    )
    assert response.status_code == 422


def test_without_a_session_hook_only_tokens_work(tmp_path: Path, world: World) -> None:
    _, token = _new_token(world)
    app = FastAPI()
    app.include_router(upload_routes.router)
    app.state.integrations = world.integrations
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/devices", headers=_as(1)).status_code == 401
    ok = client.post(
        "/api/upload/check", json={"hashes": []}, headers={"Authorization": f"Bearer {token}"}
    )
    assert ok.status_code == 200
