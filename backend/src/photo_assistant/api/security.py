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
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
