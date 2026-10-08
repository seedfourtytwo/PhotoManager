"""Behind a TLS proxy on another address (Docker + ``tailscale serve``): PA_TRUSTED_PROXIES
names who may say "this request came in over https, from that client"."""

from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from photo_assistant import __main__ as cli
from photo_assistant.api.main import create_app
from photo_assistant.api.settings import Settings
from tests.api.conftest import PIN, make_settings

NAME = "photos.example.ts.net"
DOCKER_GATEWAY = "172.18.0.1"
SETUP = {"username": "c", "display_name": "C", "pin": PIN}
FROM_BROWSER = {  # what the proxy forwards for a browser that opened https://NAME
    "Origin": f"https://{NAME}",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-For": "100.64.0.7",
}


def test_only_this_machine_is_a_trusted_proxy_unless_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).trusted_proxies == "127.0.0.1"  # type: ignore[call-arg]
    monkeypatch.setenv("PA_TRUSTED_PROXIES", "172.16.0.0/12,192.168.0.0/16")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.trusted_proxies == "172.16.0.0/12,192.168.0.0/16"


def test_the_server_starts_with_the_configured_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: dict[str, object] = {}
    settings = make_settings(tmp_path / "data", trusted_proxies="172.16.0.0/12")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: started.update(options))
    assert cli.main([]) == 0
    assert started["proxy_headers"] is True
    assert started["forwarded_allow_ips"] == "172.16.0.0/12"


@pytest.mark.parametrize(
    ("trusted", "works"),
    [("127.0.0.1", False), (DOCKER_GATEWAY, True), ("172.16.0.0/12", True), ("10.0.0.0/8", False)],
)
def test_https_from_the_browser_is_believed_only_from_a_trusted_proxy(
    tmp_path: Path, trusted: str, works: bool
) -> None:
    settings = make_settings(tmp_path / "data", allowed_hosts=[NAME], trusted_proxies=trusted)
    served = ProxyHeadersMiddleware(create_app(settings), trusted_hosts=settings.trusted_proxies)
    with TestClient(served, base_url=f"http://{NAME}", client=(DOCKER_GATEWAY, 40000)) as c:
        created = c.post("/api/setup", json=SETUP, headers=FROM_BROWSER)
        if not works:
            assert created.status_code == 403, "an https Origin on what looks like plain http"
            return
        assert created.status_code == 201
        assert "Secure" in created.headers["set-cookie"]
