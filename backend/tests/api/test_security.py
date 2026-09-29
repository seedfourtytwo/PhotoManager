"""QA M1: no login until M2, so the server must not be reachable through other websites."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(data_root=tmp_path / "data", worker_enabled=False)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8420") as c:
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
