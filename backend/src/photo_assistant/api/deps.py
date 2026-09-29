"""Shared FastAPI dependencies: services, the logged-in user, lookups that 404."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from photo_assistant.api.services import Services
from photo_assistant.domain.access import Level, User, Viewer
from photo_assistant.domain.model import Source
from photo_assistant.ports.library import AssetView

SESSION_COOKIE = "pa_session"


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


def current_user(request: Request, services: ServicesDep) -> User:
    """Every /api route except health, setup and login depends on this (401 without)."""
    token = request.cookies.get(SESSION_COOKIE)
    user = services.accounts.authenticate(token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "log in first")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_viewer(user: CurrentUser) -> Viewer:
    return Viewer.of(user)


ViewerDep = Annotated[Viewer, Depends(current_viewer)]


def admin_user(user: CurrentUser) -> User:
    if not Viewer.of(user).is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only an admin can do this")
    return user


AdminUser = Annotated[User, Depends(admin_user)]
ADMIN_ONLY = [Depends(admin_user)]
LOGGED_IN = [Depends(current_user)]


def require_source(services: Services, source_id: int) -> Source:
    source = services.repo.get_source(source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    return source


def require_view(
    services: Services,
    viewer: Viewer,
    asset_id: int,
    level: Level = Level.VIEW,
    *,
    trashed: bool = False,
) -> AssetView:
    """The photo as this viewer sees it: 404 if hidden from them, 403 if their level is too low."""
    view = services.repo.get_view(viewer, asset_id, trashed=trashed)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    if view.level < level:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"you need '{level.label}' access for this")
    return view


def require_views(
    services: Services, viewer: Viewer, ids: list[int], level: Level, *, trashed: bool = False
) -> list[AssetView]:
    """All of ids or an error: 404 if any is hidden from the viewer, 403 if any is below
    level."""
    views = services.repo.views_by_ids(viewer, ids, trashed=trashed)
    if len(views) != len(set(ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "some of these photos were not found")
    if any(v.level < level for v in views):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"you need '{level.label}' access for this")
    return views
