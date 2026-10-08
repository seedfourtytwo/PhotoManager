"""QA M1: no login until M2, so the server must not be reachable through other websites."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import Settings
from tests.api.conftest import PIN, make_settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(
        create_app(make_settings(tmp_path / "data")), base_url="http://127.0.0.1:8420"
    ) as c:
        body = {"username": "admin", "display_name": "C", "pin": PIN}
        assert c.post("/api/setup", json=body).status_code == 201
        yield c


def test_requests_for_other_host_names_are_refused(client: TestClient) -> None:
    """DNS rebinding: attacker.example resolving to 127.0.0.1 must not reach the library."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/assets", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/api/health", headers={"Host": "localhost:8420"}).status_code == 200


def test_cross_site_writes_are_refused(client: TestClient) -> None:
    evil = {"Origin": "https://attacker.example"}
    assert client.post("/api/sources/scan-all", headers=evil).status_code == 403
    fetch_meta = {"Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/sources/scan-all", headers=fetch_meta).status_code == 403
    same = {"Origin": "http://127.0.0.1:8420", "Sec-Fetch-Site": "same-origin"}
    assert client.post("/api/sources/scan-all", headers=same).status_code == 202
    assert client.post("/api/sources/scan-all").status_code == 202, "CLI tools send no Origin"


def test_reads_from_other_sites_are_allowed_to_fail_closed(client: TestClient) -> None:
    """Images embedded by other sites: allowed only for same-site fetch metadata."""
    cross = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors"}
    assert client.get("/api/stats", headers=cross).status_code == 403


def test_extra_host_names_can_be_allowed_for_tailscale(tmp_path: Path) -> None:
    settings = Settings(
        data_root=tmp_path / "data",
        worker_enabled=False,
        allowed_hosts=["127.0.0.1", "localhost", "photos.example.ts.net"],
    )
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/health", headers={"Host": "photos.example.ts.net"}).status_code == 200


def test_origin_must_match_scheme_host_and_port(client: TestClient) -> None:
    other_port = {"Origin": "http://127.0.0.1:9999"}
    assert client.post("/api/sources/scan-all", headers=other_port).status_code == 403
    assert (
        client.post(
            "/api/sources/scan-all", headers={"Origin": "http://127.0.0.1:8420"}
        ).status_code
        == 202
    )


def test_odd_header_bytes_do_not_crash_the_guard() -> None:
    """Header bytes are latin-1; a raw 0xE9 must not raise (test clients can't send it)."""
    import asyncio

    from photo_assistant.api.security import CrossSiteGuard

    reached = []

    async def app(scope: object, receive: object, send: object) -> None:
        reached.append(True)

    guard = CrossSiteGuard(app, ["127.0.0.1"])
    scope = {"type": "http", "method": "GET", "headers": [(b"x-name", b"caf\xe9")]}
    asyncio.run(guard(scope, None, None))  # type: ignore[arg-type]
    assert reached == [True]


# --- request size and content sniffing ---------------------------------------------------------

LOGIN = "/api/auth/login"
JSON = {"Content-Type": "application/json"}


def _login_body(size: int) -> bytes:
    """A well-formed login of about ``size`` bytes: only its length is wrong."""
    return b'{"username": "admin", "pin": "' + b"0" * size + b'"}'


def test_an_oversized_body_is_refused_by_its_declared_length(client: TestClient) -> None:
    anon = TestClient(client.app, base_url="http://127.0.0.1:8420")
    huge = anon.post(LOGIN, content=_login_body(3_000_000), headers=JSON)
    assert huge.status_code == 413 and "too large" in huge.json()["detail"]
    usual = anon.post(LOGIN, content=_login_body(900_000), headers=JSON)
    assert usual.status_code == 422, "under the limit it is read, and judged for what it says"


def test_an_oversized_body_sent_without_a_length_is_cut_off_while_streaming(
    client: TestClient,
) -> None:
    anon = TestClient(client.app, base_url="http://127.0.0.1:8420")
    body = _login_body(3_000_000)
    chunks = (body[i : i + 65_536] for i in range(0, len(body), 65_536))
    streamed = anon.post(LOGIN, content=chunks, headers=JSON)
    assert "content-length" not in streamed.request.headers
    assert streamed.status_code == 413 and "too large" in streamed.json()["detail"]


def test_uploads_are_not_held_to_the_small_body_limit(client: TestClient) -> None:
    files = [("file", ("notes.bin", b"x" * 1_500_000, "application/octet-stream"))]
    response = client.post("/api/upload", files=files)
    assert response.status_code == 200, "its own per-file limit applies (PA_UPLOAD_MAX_MB)"
    assert [f["outcome"] for f in response.json()["files"]] == ["rejected"], "not a photo"


def test_every_response_tells_the_browser_not_to_guess_content_types(client: TestClient) -> None:
    responses = [
        client.get("/api/health"),
        client.get("/api/assets/999/thumb"),  # 404
        client.post("/api/sources/scan-all", headers={"Origin": "https://attacker.example"}),
        client.get("/api/health", headers={"Host": "attacker.example"}),
        client.post(LOGIN, content=_login_body(3_000_000), headers=JSON),
    ]
    assert [r.status_code for r in responses] == [200, 404, 403, 400, 413]
    for response in responses:
        assert response.headers["x-content-type-options"] == "nosniff", response.status_code
