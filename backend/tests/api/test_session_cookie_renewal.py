"""The browser's session cookie lives 30 days from when it was SET, the server's session 30
days from its last USE. So the cookie is sent again once half of its life is over: someone
who opens the app every day is never signed out by the browser.

The server cannot see a cookie's age. A second cookie, ``pa_session_fresh``, is set with the
session cookie and lives 15 days: when the browser stops sending it, half the life is over."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from httpx import Response

from tests.api.conftest import BASE, PIN, services_of

DAY = timedelta(days=1)
MONTH, HALF = 30 * 24 * 3600, 15 * 24 * 3600


class MovableClock:
    def __init__(self) -> None:
        self.current = datetime.now(UTC)

    def now(self) -> datetime:
        return self.current


def _with_clock(client: TestClient) -> MovableClock:
    clock = MovableClock()
    services_of(client).accounts._clock = clock
    return clock


def _cookies(response: Response) -> dict[str, str]:
    """Cookie name → the whole Set-Cookie line."""
    return {line.split("=", 1)[0]: line for line in response.headers.get_list("set-cookie")}


def _browser_forgets_the_marker(client: TestClient) -> None:
    """What a browser does after 15 days; the test client's jar runs on the real clock."""
    client.cookies.delete("pa_session_fresh")


def test_signing_in_sets_the_session_for_30_days_and_its_marker_for_15(anon: TestClient) -> None:
    created = anon.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})

    cookies = _cookies(created)
    assert set(cookies) == {"pa_session", "pa_session_fresh"}
    assert f"Max-Age={MONTH}" in cookies["pa_session"]
    assert f"Max-Age={HALF}" in cookies["pa_session_fresh"]
    for line in cookies.values():
        assert "HttpOnly" in line and "SameSite=strict" in line and "Path=/" in line
        assert "Secure" not in line


def test_a_fresh_cookie_is_not_sent_again(admin: TestClient) -> None:
    clock = _with_clock(admin)
    for _ in range(3):
        clock.current += DAY
        used = admin.get("/api/auth/me")
        assert used.status_code == 200 and "set-cookie" not in used.headers


def test_after_15_days_of_daily_use_the_same_cookie_is_sent_again(admin: TestClient) -> None:
    clock = _with_clock(admin)
    token = admin.cookies["pa_session"]
    clock.current += 16 * DAY
    _browser_forgets_the_marker(admin)

    used = admin.get("/api/auth/me")

    cookies = _cookies(used)
    assert used.status_code == 200 and set(cookies) == {"pa_session", "pa_session_fresh"}
    assert cookies["pa_session"].startswith(f"pa_session={token};"), "the same session"
    assert f"Max-Age={MONTH}" in cookies["pa_session"]
    assert f"Max-Age={HALF}" in cookies["pa_session_fresh"]
    assert "HttpOnly" in cookies["pa_session"] and "SameSite=strict" in cookies["pa_session"]
    assert "set-cookie" not in admin.get("/api/auth/me").headers, "once, not on every request"


def test_used_every_day_for_three_months_the_browser_never_drops_the_session(
    admin: TestClient,
) -> None:
    clock = _with_clock(admin)
    issued, renewals = clock.current, 0
    for _ in range(90):
        clock.current += DAY
        assert clock.current - issued < 30 * DAY, "the browser would have dropped the cookie"
        if clock.current - issued >= 15 * DAY:
            _browser_forgets_the_marker(admin)
        used = admin.get("/api/auth/me")
        assert used.status_code == 200
        if "set-cookie" in used.headers:
            issued, renewals = clock.current, renewals + 1
    assert renewals == 6, "one every 15 days"


def test_a_client_that_keeps_no_marker_gets_the_cookie_at_most_once_a_minute(
    admin: TestClient,
) -> None:
    """A script that sends only ``pa_session``: no Set-Cookie on each of its requests."""
    clock = _with_clock(admin)
    clock.current += timedelta(minutes=5)
    _browser_forgets_the_marker(admin)
    assert "set-cookie" in admin.get("/api/auth/me").headers
    _browser_forgets_the_marker(admin)
    clock.current += timedelta(seconds=20)
    assert "set-cookie" not in admin.get("/api/auth/me").headers


def test_a_response_that_is_not_json_carries_the_renewed_cookie_too(admin: TestClient) -> None:
    """Thumbnails and downloads answer with a Response of their own."""
    clock = _with_clock(admin)
    clock.current += 16 * DAY
    _browser_forgets_the_marker(admin)

    missing = admin.get("/api/assets/999/thumb")

    assert missing.status_code == 404 and set(_cookies(missing)) == {
        "pa_session",
        "pa_session_fresh",
    }


def test_the_renewed_cookie_is_secure_over_https(admin: TestClient) -> None:
    clock = _with_clock(admin)
    secure = TestClient(admin.app, base_url="https://127.0.0.1")
    secure.cookies.set("pa_session", admin.cookies["pa_session"])
    clock.current += 16 * DAY

    cookies = _cookies(secure.get("/api/auth/me"))

    assert "Secure" in cookies["pa_session"] and "Secure" in cookies["pa_session_fresh"]


def test_an_expired_or_unknown_session_gets_no_cookie(admin: TestClient) -> None:
    clock = _with_clock(admin)
    clock.current += 31 * DAY
    _browser_forgets_the_marker(admin)
    expired = admin.get("/api/auth/me")
    assert expired.status_code == 401 and "set-cookie" not in expired.headers

    stranger = TestClient(admin.app, base_url=BASE)
    stranger.cookies.set("pa_session", "made-up")
    assert "set-cookie" not in stranger.get("/api/auth/me").headers


def test_signing_out_drops_the_marker_with_the_session(admin: TestClient) -> None:
    out = admin.post("/api/auth/logout")
    cookies = _cookies(out)
    assert set(cookies) == {"pa_session", "pa_session_fresh"}
    assert all("Max-Age=0" in line for line in cookies.values())
