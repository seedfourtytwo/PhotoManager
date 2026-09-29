"""Keep other websites out (there is no login until M2, so this matters).

- Host allow-list (Starlette's TrustedHostMiddleware) defeats DNS rebinding: a malicious page
  whose domain resolves to 127.0.0.1 still sends its own name in the Host header.
- The cross-site guard refuses requests the browser marks as coming from another site
  (Sec-Fetch-Site), and state-changing requests whose Origin is not one of ours.
  Command-line tools send neither header and are unaffected.
"""

from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ALLOWED_FETCH_SITES = {"same-origin", "none"}


class CrossSiteGuard:
    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.allowed_hosts = {h.lower() for h in allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._refuse(scope):
            response = PlainTextResponse("cross-site request refused", status_code=403)
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
