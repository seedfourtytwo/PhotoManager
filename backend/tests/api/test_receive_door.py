"""The receiving page's headers, and the second door for phones on the home Wi-Fi: a small
plain-http server that answers the receiving page and its two routes, and nothing else."""

import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import _domain_error, create_app
from photo_assistant.api.receive_door import PAGE_POLICY, Door, create_door_app, open_door
from photo_assistant.api.settings import Settings
from tests.api.conftest import BASE, PIN, make_settings, services_of

SETUP = {"username": "admin", "display_name": "C", "pin": PIN}


def _web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>app shell</html>")
    (web / "receive.html").write_text("<html>receive</html>")
    (web / "receive.js").write_text("// page script")
    (web / "receive.css").write_text("body{}")
    return web


def _settings(tmp_path: Path, **more: object) -> Settings:
    return make_settings(tmp_path / "data", web_dir=_web(tmp_path), send_to_device=True, **more)


@pytest.fixture
def app(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path)), base_url=BASE) as client:
        assert client.post("/api/setup", json=SETUP).status_code == 201
        yield client


def test_the_receiving_page_is_never_cached_framed_or_named_to_other_sites(
    app: TestClient,
) -> None:
    page = app.get("/receive.html")
    assert page.status_code == 200 and "receive" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["content-security-policy"] == PAGE_POLICY
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-content-type-options"] == "nosniff"
    for name in ("/receive.js", "/receive.css"):
        assert app.get(name).headers["cache-control"] == "no-store"
    assert "content-security-policy" not in app.get("/").headers, "only that page"


def test_switched_off_the_receiving_page_is_not_there(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data", web_dir=_web(tmp_path))
    with TestClient(create_app(settings), base_url=BASE) as client:
        for name in ("/receive.html", "/receive.js", "/receive.css"):
            assert client.get(name).status_code == 404
        assert "app shell" in client.get("/").text


def test_the_door_answers_the_receiving_side_and_nothing_else(app: TestClient) -> None:
    services = services_of(app)
    door = TestClient(create_door_app(services.settings, services, _domain_error), base_url=BASE)
    page = door.get("/receive.html")
    assert page.status_code == 200 and page.headers["content-security-policy"] == PAGE_POLICY
    assert door.get("/receive.js").status_code == 200
    refused = door.post("/api/handovers/look", json={"token": "nope"})
    assert refused.status_code == 404 and "does not work any more" in refused.text
    assert refused.headers["cache-control"] == "no-store"
    for method, path in [
        ("GET", "/"),
        ("GET", "/index.html"),
        ("GET", "/api/health"),
        ("GET", "/api/auth/accounts"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/handovers"),
        ("GET", "/api/handovers/options"),
        ("POST", "/api/handovers"),
        ("GET", "/api/assets"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
    ]:
        answer = door.request(method, path, json={"username": "admin", "pin": PIN})
        assert answer.status_code in (404, 405), f"{method} {path} is reachable through the door"


def test_a_link_made_in_the_library_is_collected_through_the_door(
    app: TestClient, tmp_path: Path
) -> None:
    services = services_of(app)
    user = services.accounts.get_user(1)
    assert user is not None
    _, https_token = services.handovers.create(user, [1], 10, encrypted=True, details_removed=True)
    door = TestClient(create_door_app(services.settings, services, _domain_error), base_url=BASE)
    # the door is plain http, whatever a header claims: an https link is refused there
    claimed = door.post(
        "/api/handovers/look", json={"token": https_token}, headers={"X-Forwarded-Proto": "https"}
    )
    assert claimed.status_code == 403


def test_the_door_is_closed_unless_both_settings_are_there(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path)), base_url=BASE) as client:
        services = services_of(client)
        assert open_door(services.settings, services, _domain_error) is None
        off = services.settings.model_copy(
            update={"send_to_device": False, "send_to_device_listen": "127.0.0.1:1"}
        )
        assert open_door(off, services, _domain_error) is None


@pytest.mark.parametrize("listen", ["8421", "0.0.0.0:", "host:port", "0.0.0.0:70000", ":80"])
def test_the_listen_setting_is_an_address_and_a_port(tmp_path: Path, listen: str) -> None:
    with pytest.raises(ValueError, match="send_to_device_listen"):
        make_settings(tmp_path / "data", send_to_device_listen=listen)


def test_the_door_listens_for_real_and_stops(app: TestClient) -> None:
    services = services_of(app)
    door = Door(create_door_app(services.settings, services, _domain_error), "127.0.0.1:0")
    door.start()
    try:
        for _ in range(100):
            if door.port:
                break
            time.sleep(0.05)
        port = door.port
        assert port, "the door never started listening"
        base = f"http://127.0.0.1:{port}"
        assert "receive" in httpx.get(f"{base}/receive.html").text
        assert httpx.get(f"{base}/api/health").status_code == 404
    finally:
        door.stop()
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"{base}/receive.html")


def test_the_server_opens_and_closes_the_door_with_itself(tmp_path: Path) -> None:
    settings = _settings(tmp_path, send_to_device_listen="127.0.0.1:0")
    assert settings.send_to_device_listen == "127.0.0.1:0"
    with TestClient(create_app(settings), base_url=BASE) as client:
        door = client.app.state.door  # type: ignore[attr-defined]
        for _ in range(100):
            if door.port:
                break
            time.sleep(0.05)
        port = door.port
        assert httpx.get(f"http://127.0.0.1:{port}/receive.html").status_code == 200
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://127.0.0.1:{port}/receive.html")
