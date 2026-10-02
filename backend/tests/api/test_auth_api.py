"""Setup, login, sessions and user admin over HTTP (contract api-v1: Setup & auth, Users)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from tests.api.conftest import BASE, PASSWORD, add_user, login, make_settings, user_id_of

OPEN_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/setup"),
    ("POST", "/api/setup"),
    ("POST", "/api/auth/login"),
}


def test_first_run_setup_creates_the_admin_and_logs_in(anon: TestClient) -> None:
    assert anon.get("/api/setup").json() == {"needs_admin": True}
    assert anon.get("/api/auth/me").status_code == 401
    created = anon.post(
        "/api/setup", json={"username": "c", "display_name": "C", "password": PASSWORD}
    )
    assert created.status_code == 201
    assert created.json() == {
        "id": 1,
        "username": "c",
        "display_name": "C",
        "role": "admin",
        "disabled": False,
    }
    cookie = created.headers["set-cookie"]
    assert "pa_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Secure" not in cookie, "plain http on the laptop"
    assert anon.get("/api/auth/me").json()["username"] == "c"
    assert anon.get("/api/setup").json() == {"needs_admin": False}
    again = anon.post(
        "/api/setup", json={"username": "x", "display_name": "X", "password": PASSWORD}
    )
    assert again.status_code == 409


def test_setup_refuses_short_passwords(anon: TestClient) -> None:
    short = anon.post("/api/setup", json={"username": "c", "display_name": "C", "password": "x"})
    assert short.status_code == 422
    assert "10 characters" in short.json()["detail"]


def test_session_cookie_is_secure_over_https(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path / "data"))
    with TestClient(app, base_url="https://127.0.0.1") as c:
        r = c.post("/api/setup", json={"username": "c", "display_name": "C", "password": PASSWORD})
        assert "Secure" in r.headers["set-cookie"]
        assert c.get("/api/auth/me").status_code == 200


def test_login_logout_and_wrong_password(admin: TestClient) -> None:
    other = TestClient(admin.app, base_url=BASE)
    bad = other.post("/api/auth/login", json={"username": "admin", "password": "wrong one!!"})
    assert bad.status_code == 401 and bad.json()["detail"]
    ok = other.post("/api/auth/login", json={"username": "ADMIN", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["role"] == "admin"
    assert other.get("/api/auth/me").status_code == 200
    assert other.post("/api/auth/logout").status_code == 204
    assert other.get("/api/auth/me").status_code == 401
    assert admin.get("/api/auth/me").status_code == 200, "other sessions are unaffected"


def test_login_is_rate_limited(admin: TestClient) -> None:
    other = TestClient(admin.app, base_url=BASE)
    for _ in range(10):
        r = other.post("/api/auth/login", json={"username": "admin", "password": "nope nope!"})
        assert r.status_code == 401
    blocked = other.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert blocked.status_code == 429


def test_an_admin_unlocks_a_rate_limited_account(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    other = TestClient(admin.app, base_url=BASE)
    for _ in range(10):
        other.post("/api/auth/login", json={"username": "lea", "password": "nope nope!"})
    assert (
        other.post("/api/auth/login", json={"username": "lea", "password": PASSWORD}).status_code
        == 429
    )
    assert lea.post(f"/api/users/{lea_id}/unlock").status_code == 403, "members can't unlock"
    unlocked = admin.post(f"/api/users/{lea_id}/unlock")
    assert unlocked.status_code == 204 and unlocked.content == b""
    ok = other.post("/api/auth/login", json={"username": "lea", "password": PASSWORD})
    assert ok.status_code == 200
    assert admin.post("/api/users/999/unlock").status_code == 404
    assert admin.post(f"/api/users/{lea_id}/unlock").status_code == 204, "nothing to clear is fine"


def test_guests_cannot_unlock(admin: TestClient) -> None:
    guest = add_user(admin, "gus", "guest")
    assert guest.post(f"/api/users/{user_id_of(admin, 'admin')}/unlock").status_code == 403


def test_change_password(admin: TestClient) -> None:
    wrong = admin.post(
        "/api/auth/password", json={"current_password": "not it!!!!", "new_password": "x" * 12}
    )
    assert wrong.status_code == 400
    short = admin.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert short.status_code == 422
    ok = admin.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "x" * 12}
    )
    assert ok.status_code == 204
    login(admin.app, "admin", "x" * 12)  # type: ignore[arg-type]


def test_admin_manages_users(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    users = admin.get("/api/users").json()
    assert [u["username"] for u in users] == ["admin", "lea"]
    lea_id = users[1]["id"]
    assert lea.get("/api/users").status_code == 403, "members don't manage accounts"
    dup = admin.post(
        "/api/users",
        json={"username": "Lea", "display_name": "x", "password": PASSWORD, "role": "guest"},
    )
    assert dup.status_code == 409
    patched = admin.patch(f"/api/users/{lea_id}", json={"display_name": "Léa", "role": "guest"})
    assert patched.json()["display_name"] == "Léa" and patched.json()["role"] == "guest"
    assert admin.patch("/api/users/999", json={"disabled": True}).status_code == 404
    assert admin.patch(f"/api/users/{lea_id}", json={"password": "short"}).status_code == 422
    admin.patch(f"/api/users/{lea_id}", json={"disabled": True})
    assert lea.get("/api/auth/me").status_code == 401, "disabling ends sessions"


def test_the_last_admin_cannot_be_removed(admin: TestClient) -> None:
    me = admin.get("/api/auth/me").json()
    r = admin.patch(f"/api/users/{me['id']}", json={"role": "member"})
    assert r.status_code == 409
    assert admin.patch(f"/api/users/{me['id']}", json={"disabled": True}).status_code == 409


def test_every_api_route_needs_a_session_except_the_open_ones(anon: TestClient) -> None:
    checked = 0
    for template, operations in anon.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        path = re.sub(r"\{[^}]+\}", "1", template)  # any id will do
        for method in operations:
            if (method.upper(), template) in OPEN_ROUTES:
                continue
            response = anon.request(method.upper(), path)
            assert response.status_code == 401, f"{method} {template} is open"
            checked += 1
    assert checked > 10


@pytest.mark.parametrize("role", ["member", "guest"])
def test_m1_admin_routes_are_admin_only(admin: TestClient, role: str, tmp_path: Path) -> None:
    user = add_user(admin, f"u{role}", role)
    folder = tmp_path / "folder"
    folder.mkdir()
    assert user.post("/api/sources", json={"label": "x", "path": str(folder)}).status_code == 403
    assert user.post("/api/sources/scan-all").status_code == 403
    assert user.post("/api/sources/1/scan").status_code == 403
    assert user.patch("/api/sources/1", json={"enabled": False}).status_code == 403
    assert user.get("/api/imports").status_code == 403
    assert user.get("/api/imports/1").status_code == 403
    assert user.get("/api/jobs").status_code == 403
    assert user.post("/api/jobs/1/retry").status_code == 403
    assert user.post("/api/users", json={}).status_code == 403


# --- QA A4: a new password ends the other sessions; an admin reset also revokes devices -------

NEW_PASSWORD = "another long password"


def test_changing_your_password_ends_your_other_sessions_but_keeps_this_one(
    admin: TestClient,
) -> None:
    here = add_user(admin, "lea")
    elsewhere = login(admin.app, "lea")  # type: ignore[arg-type]
    changed = here.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert changed.status_code == 204
    assert here.get("/api/auth/me").status_code == 200, "the session that changed it stays"
    assert elsewhere.get("/api/auth/me").status_code == 401, "a stolen session is cut off"
    assert admin.get("/api/auth/me").status_code == 200, "other people's sessions are untouched"


def test_an_admin_password_reset_ends_every_session_and_revokes_device_tokens(
    admin: TestClient,
) -> None:
    lea = add_user(admin, "lea")
    token = lea.post("/api/devices", json={"name": "phone", "platform": "ios"}).json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert lea.post("/api/upload/check", json={"hashes": []}, headers=bearer).status_code == 200
    lea_id = lea.get("/api/auth/me").json()["id"]

    assert admin.patch(f"/api/users/{lea_id}", json={"password": NEW_PASSWORD}).is_success

    assert lea.get("/api/auth/me").status_code == 401
    fresh = TestClient(admin.app, base_url=BASE)  # type: ignore[arg-type]
    assert fresh.post("/api/upload/check", json={"hashes": []}, headers=bearer).status_code == 401
    lea_again = login(admin.app, "lea", NEW_PASSWORD)  # type: ignore[arg-type]
    assert [d["revoked"] for d in lea_again.get("/api/devices").json()] == [True]
    assert admin.get("/api/auth/me").status_code == 200
