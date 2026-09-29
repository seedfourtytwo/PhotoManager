from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from photo_assistant.api.deps import ServicesDep, require_asset
from photo_assistant.api.schemas import AssetDetail, AssetOut, AssetPage, Origin
from photo_assistant.api.services import Services

router = APIRouter(prefix="/api/assets", tags=["assets"])

IMMUTABLE = "public, max-age=31536000, immutable"  # derivatives are named by content hash


@router.get("")
def list_assets(
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    cursor: str | None = None,
) -> AssetPage:
    try:
        page = services.repo.list_assets(limit, cursor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AssetPage(items=[AssetOut.of(a) for a in page.items], next_cursor=page.next_cursor)


@router.get("/{asset_id}")
def get_asset(services: ServicesDep, asset_id: int) -> AssetDetail:
    a = require_asset(services, asset_id)
    origins = [
        Origin(source_id=s.id, source_label=s.label, relative_path=p)
        for s, p in services.repo.origins_of(asset_id)
    ]
    return AssetDetail(
        **AssetOut.of(a).model_dump(),
        byte_size=a.byte_size,
        mime_type=a.mime_type,
        camera_make=a.camera_make,
        camera_model=a.camera_model,
        latitude=a.latitude,
        longitude=a.longitude,
        variant_of=a.variant_of,
        imported_at=a.imported_at,
        origins=origins,
    )


def _serve(services: Services, relative: str | None) -> Response:
    if relative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not generated yet")
    path = services.store.absolute(relative)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file missing from the library")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": IMMUTABLE})


@router.get("/{asset_id}/thumb")
def thumb(services: ServicesDep, asset_id: int) -> Response:
    return _serve(services, require_asset(services, asset_id).thumb_path)


@router.get("/{asset_id}/preview")
def preview(services: ServicesDep, asset_id: int) -> Response:
    a = require_asset(services, asset_id)
    return _serve(services, a.preview_path or a.thumb_path)


@router.get("/{asset_id}/original")
def original(services: ServicesDep, asset_id: int) -> Response:
    a = require_asset(services, asset_id)
    origins = services.repo.origins_of(asset_id)
    name = PurePosixPath(origins[0][1] if origins else a.library_path).name
    return FileResponse(
        services.store.absolute(a.library_path),
        media_type=a.mime_type or "application/octet-stream",
        filename=name,
    )
