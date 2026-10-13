"""Test mode (PA_TEST_MODE=1): a state reset for the E2E suite against the real backend.

It must be impossible to switch on by accident in use: it needs the explicit setting, refuses to
start unless the server only listens on and answers to loopback names, and only answers
requests coming from this machine.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.adapters.sqlite_snapshot import SqliteSnapshotter
from photo_assistant.api.main import create_app
from tests.api.conftest import BASE, PIN, add_user, make_settings, services_of

LOCAL = ("127.0.0.1", 50000)


def test_without_test_mode_there_is_no_reset(admin: TestClient) -> None:
    response = admin.post("/__test/reset", json={"users": "seed"})
    assert response.status_code in (404, 405)


@pytest.mark.parametrize(
    "overrides",
    [
        {"host": "0.0.0.0"},
        {"host": "192.168.1.20"},
        {"allowed_hosts": ["127.0.0.1", "photos.tailnet.ts.net"]},
    ],
)
def test_test_mode_refuses_to_start_beyond_this_machine(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    settings = make_settings(tmp_path / "data", test_mode=True, **overrides)
    with pytest.raises(RuntimeError, match="PA_TEST_MODE"):
        create_app(settings)


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path / "data", test_mode=True))
    with TestClient(app, base_url=BASE, client=LOCAL) as client:
        yield client


def _snapshot(client: TestClient, name: str) -> None:
    root = services_of(client).settings.data_root
    folder = root / "test-snapshots"
    folder.mkdir(exist_ok=True)
    SqliteSnapshotter(root / "library.db").snapshot(folder / f"{name}.db")


def test_reset_restores_a_snapshot_of_the_library(test_app: TestClient) -> None:
    _snapshot(test_app, "none")
    test_app.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
    _snapshot(test_app, "seed")
    add_user(test_app, "lea")
    assert len(test_app.get("/api/users").json()) == 2

    assert test_app.post("/__test/reset", json={"users": "seed"}).status_code == 204
    signed_in = TestClient(test_app.app, base_url=BASE, client=LOCAL)
    login = {"username": "c", "pin": PIN}
    assert signed_in.post("/api/auth/login", json=login).status_code == 200
    assert [u["username"] for u in signed_in.get("/api/users").json()] == ["c"]

    assert test_app.post("/__test/reset", json={"users": "none"}).status_code == 204
    assert test_app.get("/api/setup").json() == {"needs_admin": True}


def test_reset_needs_a_known_snapshot_and_a_local_caller(test_app: TestClient) -> None:
    assert test_app.post("/__test/reset", json={"users": "seed"}).status_code == 404
    assert test_app.post("/__test/reset", json={"users": "../x"}).status_code == 422
    remote = TestClient(test_app.app, base_url=BASE, client=("10.0.0.5", 5000))
    assert remote.post("/__test/reset", json={"users": "seed"}).status_code == 403


def test_reset_switches_send_to_a_device_on_for_one_test_and_off_again(
    test_app: TestClient,
) -> None:
    """The browser tests try the feature on and off against one server. Only this reset can
    flip it, and the reset only exists in test mode."""
    test_app.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
    _snapshot(test_app, "seed")
    login = {"username": "c", "pin": PIN}

    def options() -> int:
        signed_in = TestClient(test_app.app, base_url=BASE, client=LOCAL)
        assert signed_in.post("/api/auth/login", json=login).status_code == 200
        return signed_in.get("/api/handovers/options").status_code

    assert options() == 404, "off, as the product ships"
    assert test_app.post("/api/handovers/look", json={"token": "x"}).status_code == 404
    assert test_app.post("/__test/reset", json={"users": "seed", "send": True}).status_code == 204
    assert options() == 200
    gone = test_app.post("/api/handovers/look", json={"token": "x"})
    assert gone.status_code == 404 and "does not work any more" in gone.text
    assert test_app.post("/__test/reset", json={"users": "seed"}).status_code == 204
    assert options() == 404


def test_outside_test_mode_the_switch_is_the_setting_and_nothing_else(tmp_path: Path) -> None:
    for on in (False, True):
        app = create_app(make_settings(tmp_path / f"data-{on}", send_to_device=on))
        assert ("/api/handovers" in app.openapi()["paths"]) is on
        assert not [route for route in app.routes if "__test" in str(getattr(route, "path", ""))]
