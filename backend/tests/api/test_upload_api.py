"""Upload, hash check and device-token routes through the real app (streamed multipart).

Users sign in with real sessions; ``_as(n)`` is the session cookie of user ``n`` (1 is the
admin). Device tokens go through the same single auth dependency (api/deps.py).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.adapters.filesystem import Blake3Hasher
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.api.deps import SESSION_COOKIE
from photo_assistant.api.integrations import Integrations
from photo_assistant.api.main import create_app
from photo_assistant.api.settings import IntegrationSettings
from tests.api.conftest import BASE, PIN, make_settings, services_of
from tests.factories import NOW, new_asset

FIXTURES = Path(__file__).parent.parent / "fixtures" / "photos"
JPEG = (FIXTURES / "IMG_1002.JPG").read_bytes()
PNG = (FIXTURES / "grey-1x1.png").read_bytes()
MONTH = "2026-09"


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class World:
    client: TestClient  # no cookies of its own: each request says who it is
    repo: SqliteRepository
    integrations: Integrations
    data: Path
    sessions: dict[int, str]


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    data = tmp_path / "data"
    settings = make_settings(data, integrations=IntegrationSettings(upload_max_mb=0.01))
    app = create_app(settings)
    with TestClient(app, base_url=BASE) as admin:
        admin.post("/api/setup", json={"username": "u1", "display_name": "U1", "pin": PIN})
        sessions = {1: admin.cookies[SESSION_COOKIE]}
        for n in (2, 3, 4):
            body = {"username": f"u{n}", "display_name": f"U{n}", "pin": PIN}
            assert admin.post("/api/users", json=body | {"role": "member"}).status_code == 201
            other = TestClient(app, base_url=BASE)
            assert other.post("/api/auth/login", json={"username": f"u{n}", "pin": PIN})
            sessions[n] = other.cookies[SESSION_COOKIE]
        services = services_of(admin)
        services.integrations.upload._clock = FixedClock()  # type: ignore[attr-defined]
        yield World(
            TestClient(app, base_url=BASE),
            services.repo,
            services.integrations,
            data,
            sessions,
        )


_SESSIONS: dict[int, str] = {}


@pytest.fixture(autouse=True)
def _remember_sessions(world: World) -> None:
    _SESSIONS.clear()
    _SESSIONS.update(world.sessions)


def _as(user: int) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={_SESSIONS[user]}"}


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
        p
        for p in world.data.parent.rglob("*")
        if p.is_file() and "library.db" not in p.name and p.parent.name != "logs"
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
        (
            f"--{boundary}\r\n"
            "Content-Disposition: form-data; name=\"file\"; filename*=UTF-8''caf%C3%A9.jpg\r\n"
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode()
        + JPEG
        + f"\r\n--{boundary}--\r\n".encode()
    )
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
    body = b'--x\r\nContent-Disposition: form-data; name="f"; filename="a.jpg"\r\n\r\n' + JPEG
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


def test_a_multipart_type_without_boundary_is_a_bad_request(world: World) -> None:
    headers = {**_as(1), "Content-Type": "multipart/form-data"}
    assert world.client.post("/api/upload", content=b"x", headers=headers).status_code == 400


def test_garbled_part_headers_are_a_bad_request(world: World) -> None:
    body = b"--x\r\nBad Header Without Colon\r\n\r\ndata\r\n--x--\r\n"
    headers = {**_as(1), "Content-Type": "multipart/form-data; boundary=x"}
    response = world.client.post("/api/upload", content=body, headers=headers)
    assert response.status_code == 400
    assert "broken upload" in response.json()["detail"]


def test_photos_stored_before_a_failure_are_still_queued_for_import(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_accept = world.integrations.upload.accept
    calls = []

    def accept_then_fail(viewer, name: str, spooled):  # type: ignore[no-untyped-def]
        calls.append(name)
        if len(calls) > 1:
            raise OSError("disk full")
        return real_accept(viewer, name, spooled)

    monkeypatch.setattr(world.integrations.upload, "accept", accept_then_fail)
    files = [("file", ("a.jpg", JPEG)), ("file", ("b.png", PNG))]
    with pytest.raises(OSError, match="disk full"):
        world.client.post("/api/upload", files=files, headers=_as(1))
    assert _inbox_files(world, 1) == {f"{MONTH}/a.jpg"}
    assert len(world.repo.list_jobs()) == 1


def test_guests_are_refused_and_a_disabled_accounts_token_stops_working(world: World) -> None:
    """One dependency (session or device token) for every upload route, failing closed (B18)."""
    _, token = _new_token(world, user=4)
    bearer = {"Authorization": f"Bearer {token}"}
    admin = _as(1)
    assert world.client.patch("/api/users/3", json={"role": "guest"}, headers=admin).is_success
    guest = world.client.post("/api/upload/check", json={"hashes": []}, headers=_as(3))
    assert guest.status_code == 403
    assert world.client.post("/api/upload/check", json={"hashes": []}, headers=bearer).is_success
    assert world.client.patch("/api/users/4", json={"disabled": True}, headers=admin).is_success
    disabled = world.client.post("/api/upload/check", json={"hashes": []}, headers=bearer)
    assert disabled.status_code == 401
