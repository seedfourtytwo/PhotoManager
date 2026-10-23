"""Setup, login, sessions and user admin over HTTP (contract api-v1: Setup & auth, Users)."""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.domain.access import FAILED_LOGIN_WINDOW, LOCK_AFTER_FAILED_PINS
from tests.api.conftest import (
    BASE,
    PIN,
    add_user,
    login,
    make_settings,
    services_of,
    user_id_of,
)

OPEN_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/setup"),
    ("POST", "/api/setup"),
    ("GET", "/api/auth/accounts"),
    ("POST", "/api/auth/login"),
}


def test_first_run_setup_creates_the_admin_and_logs_in(anon: TestClient) -> None:
    assert anon.get("/api/setup").json() == {"needs_admin": True}
    assert anon.get("/api/auth/me").status_code == 401
    created = anon.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
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
    again = anon.post("/api/setup", json={"username": "x", "display_name": "X", "pin": PIN})
    assert again.status_code == 409


def test_setup_refuses_pins_that_are_not_four_digits(anon: TestClient) -> None:
    short = anon.post("/api/setup", json={"username": "c", "display_name": "C", "pin": "123"})
    assert short.status_code == 422
    assert "4 digits" in short.json()["detail"]


def test_session_cookie_is_secure_over_https(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path / "data"))
    with TestClient(app, base_url="https://127.0.0.1") as c:
        r = c.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
        assert "Secure" in r.headers["set-cookie"]
        assert c.get("/api/auth/me").status_code == 200


def test_login_logout_and_wrong_pin(admin: TestClient) -> None:
    other = TestClient(admin.app, base_url=BASE)
    bad = other.post("/api/auth/login", json={"username": "admin", "pin": "0000"})
    assert bad.status_code == 401 and bad.json()["detail"]
    ok = other.post("/api/auth/login", json={"username": "ADMIN", "pin": PIN})
    assert ok.status_code == 200 and ok.json()["role"] == "admin"
    assert other.get("/api/auth/me").status_code == 200
    assert other.post("/api/auth/logout").status_code == 204
    assert other.get("/api/auth/me").status_code == 401
    assert admin.get("/api/auth/me").status_code == 200, "other sessions are unaffected"


def test_logging_out_tells_the_browser_to_drop_its_cached_photos(admin: TestClient) -> None:
    """A shared browser: the next account must not open the last one's cached thumbnails."""
    out = admin.post("/api/auth/logout")
    assert out.status_code == 204
    assert out.headers["clear-site-data"] == '"cache"'
    assert "pa_session=" in out.headers["set-cookie"], "and the cookie still goes"


def test_signing_in_tells_the_browser_to_drop_the_last_accounts_cached_photos(
    tmp_path: Path,
) -> None:
    """A session that just ran out never logged out: the next account to sign in on that
    browser must not open the cached thumbnails of the one before (they are kept a year)."""
    with TestClient(create_app(make_settings(tmp_path / "data")), base_url=BASE) as c:
        first = c.post("/api/setup", json={"username": "admin", "display_name": "A", "pin": PIN})
        again = c.post("/api/auth/login", json={"username": "admin", "pin": PIN})
    for response in (first, again):
        assert response.headers["clear-site-data"] == '"cache"', response.request.url


def test_the_login_screen_lists_the_active_accounts_without_a_session(admin: TestClient) -> None:
    add_user(admin, "lea")
    gone = add_user(admin, "old")
    admin.patch(f"/api/users/{gone.get('/api/auth/me').json()['id']}", json={"disabled": True})
    other = TestClient(admin.app, base_url=BASE)
    listed = other.get("/api/auth/accounts")
    assert listed.status_code == 200
    assert listed.json() == [
        {"username": "admin", "display_name": "C"},
        {"username": "lea", "display_name": "Lea"},
    ], "names only: no ids, no roles, no disabled accounts"


def test_login_is_rate_limited(admin: TestClient) -> None:
    other = TestClient(admin.app, base_url=BASE)
    for _ in range(10):
        r = other.post("/api/auth/login", json={"username": "admin", "pin": "0000"})
        assert r.status_code == 401
    blocked = other.post("/api/auth/login", json={"username": "admin", "pin": PIN})
    assert blocked.status_code == 429


def test_the_limit_is_per_account_whatever_address_the_guesses_come_from(
    admin: TestClient,
) -> None:
    for n in range(10):
        elsewhere = TestClient(admin.app, base_url=BASE, client=(f"10.0.0.{n}", 50000))
        r = elsewhere.post("/api/auth/login", json={"username": "admin", "pin": "0000"})
        assert r.status_code == 401
    fresh = TestClient(admin.app, base_url=BASE, client=("10.0.9.9", 50000))
    blocked = fresh.post("/api/auth/login", json={"username": "admin", "pin": PIN})
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == (
        "too many wrong PINs; wait 15 minutes and try again, or ask an admin to unlock this account"
    )


def test_an_admin_unlocks_a_rate_limited_account(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    other = TestClient(admin.app, base_url=BASE)
    for _ in range(10):
        other.post("/api/auth/login", json={"username": "lea", "pin": "0000"})
    assert other.post("/api/auth/login", json={"username": "lea", "pin": PIN}).status_code == 429
    assert lea.post(f"/api/users/{lea_id}/unlock").status_code == 403, "members can't unlock"
    unlocked = admin.post(f"/api/users/{lea_id}/unlock")
    assert unlocked.status_code == 204 and unlocked.content == b""
    ok = other.post("/api/auth/login", json={"username": "lea", "pin": PIN})
    assert ok.status_code == 200
    assert admin.post("/api/users/999/unlock").status_code == 404
    assert admin.post(f"/api/users/{lea_id}/unlock").status_code == 204, "nothing to clear is fine"


def test_guests_cannot_unlock(admin: TestClient) -> None:
    guest = add_user(admin, "gus", "guest")
    assert guest.post(f"/api/users/{user_id_of(admin, 'admin')}/unlock").status_code == 403


# --- the hard lock: 30 wrong PINs since the last good sign-in ----------------------------------


def lock_out(client: TestClient, username: str) -> None:
    """Thirty wrong PINs an hour apart: ten within 15 minutes would only mean a wait."""
    services = services_of(client)
    now = services.clock.now()
    for n in range(LOCK_AFTER_FAILED_PINS):
        at = now - timedelta(hours=LOCK_AFTER_FAILED_PINS - n)
        tried = services.repo.record_login_attempt(
            username, f"10.0.0.{n}", at, at - FAILED_LOGIN_WINDOW
        )
        assert tried.allowed


def locked_flags(admin: TestClient) -> dict[str, bool]:
    return {u["username"]: u["locked"] for u in admin.get("/api/users").json()}


def test_a_locked_account_refuses_the_right_pin_until_an_admin_unlocks_it(
    admin: TestClient,
) -> None:
    lea = add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    assert locked_flags(admin) == {"admin": False, "lea": False}
    lock_out(admin, "lea")
    other = TestClient(admin.app, base_url=BASE)
    refused = other.post("/api/auth/login", json={"username": "LEA", "pin": PIN})
    assert refused.status_code == 423
    assert refused.json()["detail"] == (
        "this account is locked after too many wrong PINs; ask an admin to unlock it, "
        "or set a new PIN on the server with 'just set-pin'"
    )
    assert "set-cookie" not in refused.headers
    assert locked_flags(admin) == {"admin": False, "lea": True}
    assert lea.post(f"/api/users/{lea_id}/unlock").status_code == 403, "not by themselves"
    assert admin.post(f"/api/users/{lea_id}/unlock").status_code == 204
    assert locked_flags(admin) == {"admin": False, "lea": False}
    ok = other.post("/api/auth/login", json={"username": "lea", "pin": PIN})
    assert ok.status_code == 200 and "locked" not in ok.json()


def test_the_fifteen_minute_wait_shows_as_locked_to_admins_and_unlock_lifts_it(
    admin: TestClient,
) -> None:
    add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    other = TestClient(admin.app, base_url=BASE)
    for _ in range(9):
        other.post("/api/auth/login", json={"username": "lea", "pin": "0000"})
    assert locked_flags(admin) == {"admin": False, "lea": False}, "one try is left"
    other.post("/api/auth/login", json={"username": "Lea", "pin": "0000"})
    assert locked_flags(admin) == {"admin": False, "lea": True}
    renamed = admin.patch(f"/api/users/{lea_id}", json={"display_name": "Léa"})
    assert renamed.json()["locked"] is True
    assert admin.post(f"/api/users/{lea_id}/unlock").status_code == 204
    assert locked_flags(admin) == {"admin": False, "lea": False}


def test_only_admins_learn_which_accounts_are_locked(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    guest = add_user(admin, "gus", "guest")
    lock_out(admin, "admin")
    assert locked_flags(admin)["admin"] is True, "the admin's open session still works"
    anyone = TestClient(admin.app, base_url=BASE)
    assert anyone.get("/api/auth/accounts").json() == [
        {"username": "admin", "display_name": "C"},
        {"username": "lea", "display_name": "Lea"},
        {"username": "gus", "display_name": "Gus"},
    ], "the open list still gives names only, the locked account among them"
    directory = lea.get("/api/users/directory").json()
    assert all(set(entry) == {"id", "display_name"} for entry in directory)
    for client in (lea, guest):
        assert client.get("/api/users").status_code == 403
        assert "locked" not in client.get("/api/auth/me").json()
        unlock = client.post(f"/api/users/{user_id_of(admin, 'admin')}/unlock")
        assert unlock.status_code == 403
    assert locked_flags(admin)["admin"] is True


def test_the_lock_outlives_the_window_the_housekeeping_and_a_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data")
    with TestClient(create_app(settings), base_url=BASE) as first:
        first.post("/api/setup", json={"username": "admin", "display_name": "C", "pin": PIN})
        add_user(first, "lea")
        lock_out(first, "lea")  # the last wrong PIN was an hour ago: no 15-minute wait is left
        services = services_of(first)
        services.ops.periodic.tick()  # the daily pruning of old failed logins
        left = services.db.writer.execute("SELECT COUNT(*) FROM login_failure").fetchone()[0]
        assert left < LOCK_AFTER_FAILED_PINS
        again = first.post("/api/auth/login", json={"username": "lea", "pin": PIN})
        assert again.status_code == 423
    with TestClient(create_app(settings), base_url=BASE) as second:
        after = second.post("/api/auth/login", json={"username": "lea", "pin": PIN})
        assert after.status_code == 423
        boss = login(second.app, "admin")  # type: ignore[arg-type]
        assert locked_flags(boss) == {"admin": False, "lea": True}


def test_an_admin_pin_reset_lifts_the_lock(admin: TestClient) -> None:
    add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    lock_out(admin, "lea")
    renamed = admin.patch(f"/api/users/{lea_id}", json={"display_name": "Léa"})
    assert renamed.json()["locked"] is True, "only a new PIN or Unlock lifts it"
    reset = admin.patch(f"/api/users/{lea_id}", json={"pin": NEW_PIN})
    assert reset.status_code == 200 and reset.json()["locked"] is False
    login(admin.app, "lea", NEW_PIN)  # type: ignore[arg-type]


def test_a_locked_account_cannot_change_its_pin_from_an_open_session(admin: TestClient) -> None:
    lock_out(admin, "admin")
    refused = admin.post("/api/auth/pin", json={"current_pin": PIN, "new_pin": NEW_PIN})
    assert refused.status_code == 423 and "locked" in refused.json()["detail"]
    assert admin.get("/api/auth/me").status_code == 200, "the open session goes on"
    assert locked_flags(admin) == {"admin": True}


def test_change_pin(admin: TestClient) -> None:
    wrong = admin.post("/api/auth/pin", json={"current_pin": "0000", "new_pin": NEW_PIN})
    assert wrong.status_code == 400
    short = admin.post("/api/auth/pin", json={"current_pin": PIN, "new_pin": "12345"})
    assert short.status_code == 422
    ok = admin.post("/api/auth/pin", json={"current_pin": PIN, "new_pin": NEW_PIN})
    assert ok.status_code == 204
    login(admin.app, "admin", NEW_PIN)  # type: ignore[arg-type]


def test_guessing_the_current_pin_is_rate_limited_like_login(admin: TestClient) -> None:
    for _ in range(10):
        wrong = admin.post("/api/auth/pin", json={"current_pin": "0000", "new_pin": NEW_PIN})
        assert wrong.status_code == 400
    for pin in ("0000", PIN):
        blocked = admin.post("/api/auth/pin", json={"current_pin": pin, "new_pin": NEW_PIN})
        assert blocked.status_code == 429 and "wait" in blocked.json()["detail"]
    assert admin.get("/api/auth/me").status_code == 200, "the session itself is untouched"


def test_admin_manages_users(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    users = admin.get("/api/users").json()
    assert [u["username"] for u in users] == ["admin", "lea"]
    lea_id = users[1]["id"]
    assert lea.get("/api/users").status_code == 403, "members don't manage accounts"
    dup = admin.post(
        "/api/users",
        json={"username": "Lea", "display_name": "x", "pin": PIN, "role": "guest"},
    )
    assert dup.status_code == 409
    patched = admin.patch(f"/api/users/{lea_id}", json={"display_name": "Léa", "role": "guest"})
    assert patched.json()["display_name"] == "Léa" and patched.json()["role"] == "guest"
    assert admin.patch("/api/users/999", json={"disabled": True}).status_code == 404
    assert admin.patch(f"/api/users/{lea_id}", json={"pin": "123"}).status_code == 422
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


# --- QA A4: a new PIN ends the other sessions; an admin reset also revokes devices -------

NEW_PIN = "5678"


def test_changing_your_pin_ends_your_other_sessions_but_keeps_this_one(
    admin: TestClient,
) -> None:
    here = add_user(admin, "lea")
    elsewhere = login(admin.app, "lea")  # type: ignore[arg-type]
    changed = here.post("/api/auth/pin", json={"current_pin": PIN, "new_pin": NEW_PIN})
    assert changed.status_code == 204
    assert here.get("/api/auth/me").status_code == 200, "the session that changed it stays"
    assert elsewhere.get("/api/auth/me").status_code == 401, "a stolen session is cut off"
    assert admin.get("/api/auth/me").status_code == 200, "other people's sessions are untouched"


def test_an_admin_pin_reset_ends_every_session_and_revokes_device_tokens(
    admin: TestClient,
) -> None:
    lea = add_user(admin, "lea")
    token = lea.post("/api/devices", json={"name": "phone", "platform": "ios"}).json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert lea.post("/api/upload/check", json={"hashes": []}, headers=bearer).status_code == 200
    lea_id = lea.get("/api/auth/me").json()["id"]

    assert admin.patch(f"/api/users/{lea_id}", json={"pin": NEW_PIN}).is_success

    assert lea.get("/api/auth/me").status_code == 401
    fresh = TestClient(admin.app, base_url=BASE)
    assert fresh.post("/api/upload/check", json={"hashes": []}, headers=bearer).status_code == 401
    lea_again = login(admin.app, "lea", NEW_PIN)  # type: ignore[arg-type]
    assert [d["revoked"] for d in lea_again.get("/api/devices").json()] == [True]
    assert admin.get("/api/auth/me").status_code == 200
