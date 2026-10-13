"""The receiving side of "send to a device" as seen from outside: its headers, and its own door.

**Headers.** The receiving page and the two token routes are the only things a device without
a session gets from this app. They are never cached and never name themselves to another
site, and the page may only run its own script and talk to its own server.

**The door** (``PA_SEND_TO_DEVICE_LISTEN``, off unless set): a second, small server on plain
http that answers *only* those addresses. It is how a phone on the home Wi-Fi, without
Tailscale, collects photos while the library itself stays on this machine behind Tailscale:
the sign-in screen, the PINs and every other route are simply not there. Nothing is in front
of it, so a request on it is never https and its client is the device itself.
"""

import logging
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from photo_assistant.api.routes import receive
from photo_assistant.api.routes.handovers import RECEIVE_PAGE
from photo_assistant.api.security import RequestLimits
from photo_assistant.api.services import Services
from photo_assistant.api.settings import Settings
from photo_assistant.domain.errors import DomainError

log = logging.getLogger(__name__)

PAGE_FILES = (RECEIVE_PAGE, "/receive.js", "/receive.css")
_TOKEN_ROUTES = tuple(f"{receive.router.prefix}{name}" for name in ("/look", "/collect"))
# The page loads its own script and style, posts to its own server (the download runs in a
# hidden frame of its own), and nothing else; no other site may frame it.
PAGE_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "form-action 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'none'"
)


class ReceiveHeaders:
    """Marks every answer of the receiving side, refusals included."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive_: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path not in PAGE_FILES and path not in _TOKEN_ROUTES:
            await self.app(scope, receive_, send)
            return

        async def send_marked(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Referrer-Policy"] = "no-referrer"
                if path == RECEIVE_PAGE:
                    headers["Content-Security-Policy"] = PAGE_POLICY
                    headers["X-Frame-Options"] = "DENY"
            await send(message)

        await self.app(scope, receive_, send_marked)


ErrorHandler = Callable[[Request, Exception], Awaitable[Response]]


def create_door_app(settings: Settings, services: Services, on_error: ErrorHandler) -> FastAPI:
    """Only the receiving page and its two routes; everything else is a 404. ``on_error``:
    the app's one handler for domain errors."""
    app = FastAPI(title="Photo Assistant: receive", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.services = services
    app.add_exception_handler(DomainError, on_error)
    app.include_router(receive.router)
    if settings.web_dir is not None:
        for name in PAGE_FILES:
            served = _file(settings.web_dir / name.lstrip("/"))
            app.add_api_route(name, served, include_in_schema=False)
    app.add_middleware(ReceiveHeaders)
    app.add_middleware(RequestLimits)
    return app


def _file(path: Path) -> Callable[[], FileResponse]:
    def serve() -> FileResponse:
        return FileResponse(path)

    return serve


class Door:
    """The door's server on a thread of its own, beside the main one."""

    def __init__(self, app: FastAPI, listen: str) -> None:
        self._listen = listen
        host, _, port = listen.rpartition(":")
        # no proxy headers: nothing is in front, so nobody may claim https or another address
        config = uvicorn.Config(app, host=host, port=int(port), proxy_headers=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="pa-door", daemon=True)

    def start(self) -> None:
        log.info("send to a device: the receiving door listens on %s", self._listen)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._server.should_exit = True
        self._thread.join(timeout)

    @property
    def port(self) -> int | None:
        """The port it really listens on (a test asks for port 0), once it has started."""
        for server in getattr(self._server, "servers", []):
            for sock in server.sockets:
                return int(sock.getsockname()[1])
        return None


def open_door(settings: Settings, services: Services, on_error: ErrorHandler) -> Door | None:
    if not settings.send_to_device or settings.send_to_device_listen is None:
        return None
    door = Door(create_door_app(settings, services, on_error), settings.send_to_device_listen)
    door.start()
    return door
