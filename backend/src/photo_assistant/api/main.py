"""FastAPI app factory. Routes live in api/routes/, one module per area."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.types import Scope

from photo_assistant import __version__
from photo_assistant.api.logging_setup import configure_logging, shutdown_logging
from photo_assistant.api.routes import (
    albums,
    assets,
    auth,
    downloads,
    edits,
    imports,
    library,
    sources,
    system,
    trash,
    users,
)
from photo_assistant.api.security import CrossSiteGuard
from photo_assistant.api.services import build_services
from photo_assistant.api.settings import Settings, get_settings


class SinglePageApp(StaticFiles):
    """Serve the built web app; unknown paths get index.html so client routing works."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def _mount_web(app: FastAPI, web_dir: Path | None) -> None:
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", SinglePageApp(directory=web_dir, html=True), name="web")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.data_root.expanduser(), settings.log_level)
        services = build_services(settings)
        app.state.services = services
        services.repo.recover_interrupted_jobs()  # only the server owns the job queue
        if settings.worker_enabled:
            services.worker.start()
        try:
            yield
        finally:
            services.close()
            shutdown_logging()

    app = FastAPI(title="Photo Assistant", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    for module in (
        system,
        auth,
        users,
        sources,
        imports,
        assets,
        edits,
        library,
        albums,
        downloads,
        trash,
    ):
        app.include_router(module.router)
    _mount_web(app, settings.web_dir)
    app.add_middleware(CrossSiteGuard, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    return app
