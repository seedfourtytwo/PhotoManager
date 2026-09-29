"""Shared FastAPI dependencies: services, the logged-in user, lookups that 404."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from photo_assistant.api.services import Services
from photo_assistant.domain.access import User, Viewer
from photo_assistant.domain.model import Asset, Source

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


def require_asset(services: Services, asset_id: int) -> Asset:
    asset = services.repo.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    return asset
