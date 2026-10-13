"""FastAPI app factory. Routes live in api/routes/, one module per area."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse, Response
from starlette.types import Scope

from photo_assistant import __version__
from photo_assistant.api.deps import path_ids_in_range
from photo_assistant.api.logging_setup import configure_logging, shutdown_logging
from photo_assistant.api.receive_door import PAGE_FILES, ReceiveHeaders, open_door
from photo_assistant.api.routes import (
    albums,
    assets,
    auth,
    backup,
    downloads,
    edits,
    folders,
    handovers,
    imports,
    library,
    look,
    ml,
    printing,
    proton,
    receive,
    remote_sources,
    review,
    sources,
    system,
    testing,
    trash,
    upload,
    users,
)
from photo_assistant.api.security import CrossSiteGuard, RequestLimits, SessionCookieRenewal
from photo_assistant.api.send_switch import switch, switched_on
from photo_assistant.api.services import Services, build_services
from photo_assistant.api.settings import Settings, get_settings, warn_about_unknown_settings
from photo_assistant.domain.errors import DomainError, UnavailableError
from photo_assistant.ports.sync import SyncError

IMMUTABLE_BUILD = "public, max-age=31536000, immutable"
# Compressed: JSON and the web build. Never: what is compressed already, or streamed files
# (photos, ZIPs, PDFs, originals) — gzip would only cost CPU (C30).
_NOT_GZIPPED = (*DEFAULT_EXCLUDED_CONTENT_TYPES, "application/pdf", "application/octet-stream")


class SinglePageApp(StaticFiles):
    """Serve the built web app; unknown paths get index.html so client routing works.
    Files under ``_app/immutable/`` carry a content hash in their name: cached for good."""

    def __init__(self, *, directory: Path, hidden: Callable[[], frozenset[str]]) -> None:
        super().__init__(directory=directory, html=True)
        self._hidden = hidden  # files of a feature that is switched off: not there

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path in self._hidden():
            return PlainTextResponse("Not Found", status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)
        if path.startswith("_app/immutable/"):
            response.headers["Cache-Control"] = IMMUTABLE_BUILD
        return response


def _mount_web(app: FastAPI, settings: Settings) -> None:
    web_dir = settings.web_dir
    if web_dir is not None and (web_dir / "index.html").is_file():
        receiving = frozenset(name.lstrip("/") for name in PAGE_FILES)

        def hidden() -> frozenset[str]:
            return frozenset() if switched_on(app) else receiving

        app.mount("/", SinglePageApp(directory=web_dir, hidden=hidden), name="web")


def _install_services(app: FastAPI, services: Services) -> None:
    app.state.services = services  # read in one place: deps.get_services


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    """THE error handler: every DomainError becomes its status and ``{"detail": message}``."""
    assert isinstance(exc, DomainError)
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


async def _sync_error(request: Request, exc: Exception) -> JSONResponse:
    """A pull-side failure met while answering a request (listing a provider's folders,
    naming a remote). One that waiting cannot fix is a DomainError and keeps its status; the
    rest may pass (the network, a slow provider): 503, try again."""
    code = exc.status if isinstance(exc, DomainError) else UnavailableError.status
    return JSONResponse({"detail": str(exc)}, status_code=code)


def _check_test_mode(settings: Settings) -> None:
    """Test mode resets the library: refuse it unless the server stays on this machine."""
    names = [settings.host, *settings.allowed_hosts]
    if not all(testing.is_loopback(name) for name in names):
        raise RuntimeError(
            "PA_TEST_MODE=1 resets the library: it only runs with PA_HOST=127.0.0.1 and "
            "loopback PA_ALLOWED_HOSTS. Never set it on a real library."
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.test_mode:
        _check_test_mode(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.data_root.expanduser(), settings.log_level)
        warn_about_unknown_settings()
        services = build_services(settings, role="server")
        _install_services(app, services)
        # jobs cut off by a crash; never one that a running CLI command still renews
        services.stale_jobs.run()
        services.store.sweep_tmp()  # never from a CLI command: it would cut a running upload
        if settings.worker_enabled:
            services.start_background()
        door = open_door(settings, services, _domain_error)  # None unless switched on
        app.state.door = door
        try:
            yield
        finally:
            if door is not None:
                door.stop()
            services.close()
            shutdown_logging()

    app = FastAPI(
        title="Photo Assistant",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(path_ids_in_range)],
    )
    app.state.settings = settings
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(SyncError, _sync_error)
    for module in (
        system,
        auth,
        users,
        look,
        sources,
        folders,
        imports,
        assets,
        edits,
        library,
        albums,
        downloads,
        trash,
        review,
        upload,
        proton,
        remote_sources,
        backup,
        ml,
        printing,
    ):
        app.include_router(module.router)
    # "Send to a device", off unless switched on: its addresses then do not exist. (Test
    # mode mounts them switched off, so the browser tests can turn the feature on and off.)
    switch(app, settings.send_to_device)
    if settings.send_to_device or settings.test_mode:
        app.include_router(handovers.router)
        app.include_router(receive.router)
    if settings.test_mode:
        app.include_router(testing.router)
    _mount_web(app, settings)
    app.add_middleware(
        GZipMiddleware, minimum_size=1024, compresslevel=6, exclude_content_types=_NOT_GZIPPED
    )
    app.add_middleware(ReceiveHeaders)
    app.add_middleware(SessionCookieRenewal)
    app.add_middleware(CrossSiteGuard, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestLimits)  # outermost: also marks the refusals of those above
    return app
