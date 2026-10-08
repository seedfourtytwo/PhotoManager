"""Keep other websites out (defence in depth next to the SameSite=Strict session cookie).

- Host allow-list (Starlette's TrustedHostMiddleware) defeats DNS rebinding: a malicious page
  whose domain resolves to 127.0.0.1 still sends its own name in the Host header.
- The cross-site guard refuses requests the browser marks as coming from another site
  (Sec-Fetch-Site), and state-changing requests whose Origin is not one of ours.
  Command-line tools send neither header and are unaffected.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from photo_assistant.domain.access import SESSION_COOKIE_RENEW_AFTER, SESSION_IDLE_LIMIT

SESSION_COOKIE = "pa_session"
# Set with the session cookie, but for half as long: a browser that no longer sends it holds
# a session cookie past half its life (the server cannot see a cookie's age).
SESSION_FRESH_COOKIE = "pa_session_fresh"
_RENEW = "renew_session"  # in the request's state: the token whose cookie is sent again

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ALLOWED_FETCH_SITES = {"same-origin", "none"}
# The largest JSON the API takes (100,000 photo ids for a download) stays under this.
MAX_BODY_BYTES = 1_000_000
# Photos are streamed to disk under their own per-file limit (PA_UPLOAD_MAX_MB).
UPLOAD_PATHS = frozenset({"/api/upload"})
_TOO_LARGE = "request body too large"


class RequestLimits:
    """Refuses (413) a request body over ``MAX_BODY_BYTES`` before anything parses it: by its
    declared length, or while it streams in when it declares none. Uploads are exempt.
    Also marks every response ``nosniff``: the browser takes our content types as given."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_nosniff(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Content-Type-Options"] = "nosniff"
            await send(message)

        if scope["path"] in UPLOAD_PATHS:
            await self.app(scope, receive, send_nosniff)
            return
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            response = JSONResponse({"detail": _TOO_LARGE}, status_code=413)
            await response(scope, receive, send_nosniff)
            return
        await self.app(scope, _limited(receive), send_nosniff)


def _limited(receive: Receive) -> Receive:
    """``receive``, but it raises once more than ``MAX_BODY_BYTES`` of body have come in.
    That happens where the route reads its body, and the app answers it as a 413."""
    received = 0

    async def limited_receive() -> Message:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > MAX_BODY_BYTES:
                raise HTTPException(413, _TOO_LARGE)
        return message

    return limited_receive


class CrossSiteGuard:
    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.allowed_hosts = {h.lower() for h in allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._refuse(scope):
            response = JSONResponse({"detail": "cross-site request refused"}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _refuse(self, scope: Scope) -> bool:
        # HTTP header bytes are latin-1 by definition; decoding as UTF-8 could crash.
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site is not None and fetch_site.lower() not in _ALLOWED_FETCH_SITES:
            return True
        origin = headers.get("origin")
        if scope["method"] in _SAFE_METHODS or origin is None:
            return False
        return not self._same_origin(origin, headers.get("host", ""), scope.get("scheme", "http"))

    def _same_origin(self, origin: str, host: str, scheme: str) -> bool:
        """Origin must be exactly this server: same scheme, host (allowed) and port."""
        parts = urlsplit(origin)
        if (parts.hostname or "").lower() not in self.allowed_hosts:
            return False
        return parts.scheme == scheme and parts.netloc.lower() == host.lower()


def set_session_cookies(response: Response, token: str, *, secure: bool) -> None:
    """The session cookie for as long as an unused session lives, and its marker."""
    for name, value, life in (
        (SESSION_COOKIE, token, SESSION_IDLE_LIMIT),
        (SESSION_FRESH_COOKIE, "1", SESSION_COOKIE_RENEW_AFTER),
    ):
        response.set_cookie(
            name,
            value,
            max_age=int(life.total_seconds()),
            httponly=True,
            samesite="strict",
            secure=secure,
            path="/",
        )


def clear_session_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, SESSION_FRESH_COOKIE):
        response.delete_cookie(name, path="/")


def renew_session_cookie(scope: Scope, token: str) -> None:
    """Ask for this request's response to carry the session cookie again."""
    scope.setdefault("state", {})[_RENEW] = token


class SessionCookieRenewal:
    """Sends the session cookie again with the response of a request that asked for it
    (``renew_session_cookie``): whatever the route answers with, also a file or an error.

    The browser counts the cookie's 30 days from when it was set, the server counts a
    session's 30 days from its last use: without this, daily use still ends after 30 days."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})  # the same dict the route's request.state uses

        async def send_renewed(message: Message) -> None:
            token = state.get(_RENEW)
            if message["type"] == "http.response.start" and token:
                cookies = Response()
                set_session_cookies(cookies, token, secure=scope["scheme"] == "https")
                headers = MutableHeaders(scope=message)
                for line in cookies.headers.getlist("set-cookie"):
                    headers.append("set-cookie", line)
            await send(message)

        await self.app(scope, receive, send_renewed)
