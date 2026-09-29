"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from photo_assistant.api.services import Services
from photo_assistant.domain.model import Asset, Source


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


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
