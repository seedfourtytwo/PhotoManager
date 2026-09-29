"""The timeline, one photo, its images and per-user state (contract: Assets)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep, require_view
from photo_assistant.api.filters import FilterDep
from photo_assistant.api.schemas import (
    AlbumRef,
    AssetDetail,
    AssetOut,
    AssetPage,
    BulkState,
    FacetsOut,
    NameCount,
    Origin,
    SourceCount,
    StatePatch,
    Updated,
    YearCount,
)
from photo_assistant.api.services import Services
from photo_assistant.domain.access import Level, Viewer
from photo_assistant.ports.library import AssetView

router = APIRouter(prefix="/api/assets", tags=["assets"], dependencies=LOGGED_IN)

# Image URLs carry ?v=<edit version>, so a response never changes for its URL.
IMMUTABLE = "private, max-age=31536000, immutable"


def asset_out(services: Services, view: AssetView) -> AssetOut:
    return AssetOut.of(view)


@router.get("")
def list_assets(
    services: ServicesDep,
    viewer: ViewerDep,
    f: FilterDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    cursor: str | None = None,
) -> AssetPage:
    try:
        page = services.repo.list_views(viewer, f, limit, cursor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AssetPage(
        items=[asset_out(services, v) for v in page.items], next_cursor=page.next_cursor
    )


@router.get("/facets")
def facets(services: ServicesDep, viewer: ViewerDep, f: FilterDep) -> FacetsOut:
    found = services.repo.facets(viewer, f)
    return FacetsOut(
        years=[YearCount(year=int(c.key), count=c.count) for c in found.years],
        sources=[SourceCount(id=int(c.key), label=c.label, count=c.count) for c in found.sources],
        cameras=[NameCount(name=c.key, count=c.count) for c in found.cameras],
        places=[NameCount(name=c.key, count=c.count) for c in found.places],
        guessed_dates=found.guessed_dates,
        total=found.total,
    )


@router.post("/state")
def bulk_state(services: ServicesDep, viewer: ViewerDep, body: BulkState) -> Updated:
    """Favourite / hide many at once; photos you can't see are ignored."""
    visible = [v.id for v in services.repo.views_by_ids(viewer, body.ids)]
    updated = services.repo.set_user_state(
        viewer.user_id, visible, favourite=body.favourite, hidden=body.hidden
    )
    return Updated(updated=updated)


def detail_of(services: Services, viewer: Viewer, view: AssetView) -> AssetDetail:
    a = view.asset
    origins = [
        Origin(source_id=s.id, source_label=s.label, relative_path=p)
        for s, p in services.repo.origins_for(viewer, a.id)
    ]
    albums = [AlbumRef(id=i, title=t) for i, t in services.repo.albums_of(viewer, a.id)]
    return AssetDetail(
        **asset_out(services, view).model_dump(),
        byte_size=a.byte_size,
        mime_type=a.mime_type,
        camera_make=a.camera_make,
        camera_model=a.camera_model,
        latitude=a.latitude,
        longitude=a.longitude,
        imported_at=a.imported_at,
        origins=origins,
        albums=albums,
        level=view.level.label,  # type: ignore[arg-type]  # a LevelName by construction
    )


@router.get("/{asset_id}")
def get_asset(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> AssetDetail:
    return detail_of(services, viewer, require_view(services, viewer, asset_id))


@router.patch("/{asset_id}/state")
def patch_state(
    services: ServicesDep, viewer: ViewerDep, asset_id: int, body: StatePatch
) -> AssetOut:
    view = require_view(services, viewer, asset_id)
    if body.private is not None:
        if not (viewer.is_admin or view.owner_id == viewer.user_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "only the photo's owner or an admin can do this"
            )
        services.repo.set_private(asset_id, body.private)
    if body.favourite is not None or body.hidden is not None:
        services.repo.set_user_state(
            viewer.user_id, [asset_id], favourite=body.favourite, hidden=body.hidden
        )
    return asset_out(services, require_view(services, viewer, asset_id))


def _serve_webp(services: Services, view: AssetView, kind: str) -> Response:
    path = services.editor.image_for(view, kind)
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not generated yet")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": IMMUTABLE})


@router.get("/{asset_id}/thumb")
def thumb(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> Response:
    return _serve_webp(services, require_view(services, viewer, asset_id), "thumb")


@router.get("/{asset_id}/preview")
def preview(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> Response:
    return _serve_webp(services, require_view(services, viewer, asset_id), "preview")


@router.get("/{asset_id}/original")
def original(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> Response:
    a = require_view(services, viewer, asset_id, Level.DOWNLOAD).asset
    path = services.store.absolute(a.library_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "original missing from the library")
    name = services.repo.first_origin_name(asset_id) or path.name
    return FileResponse(path, media_type=a.mime_type or "application/octet-stream", filename=name)
