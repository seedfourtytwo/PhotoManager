"""The timeline, one photo, its images and per-user state (contract: Assets)."""

from dataclasses import replace
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from photo_assistant.api.deps import (
    LOGGED_IN,
    ServicesDep,
    ViewerDep,
    require_view,
    require_views,
)
from photo_assistant.api.filters import FilterDep
from photo_assistant.api.schemas import (
    AlbumRef,
    AssetDetail,
    AssetOut,
    AssetPage,
    BulkState,
    DatesIn,
    FacetsOut,
    NameCount,
    Origin,
    SourceCount,
    StatePatch,
    Updated,
    YearCount,
)
from photo_assistant.api.services import Services
from photo_assistant.app.enrich import FULL_REGROUP, GROUP_JOB
from photo_assistant.domain.access import Level, Viewer
from photo_assistant.domain.date_fix import new_capture_times
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


@router.post("/dates")
def fix_dates(services: ServicesDep, viewer: ViewerDep, body: DatesIn) -> Updated:
    """Set or shift capture times (needs edit on every photo); previous values are kept."""
    if (body.set is None) == (body.shift_minutes is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "give exactly one of 'set' or 'shift_minutes'"
        )
    views = require_views(services, viewer, body.ids, Level.EDIT)
    old = [(v.id, v.asset.taken_at) for v in views]
    local_now = services.clock.now().astimezone().replace(tzinfo=None)
    changes = new_capture_times(old, body.set, body.shift_minutes, local_now)  # DateFixError: 422
    updated = services.repo.change_dates(changes, viewer.user_id, services.clock.now())
    services.repo.enqueue_once(GROUP_JOB, FULL_REGROUP)  # moved photos may change groups
    return Updated(updated=updated)


@router.get("/{asset_id}")
def get_asset(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> AssetDetail:
    return detail_of(services, viewer, require_view(services, viewer, asset_id))


@router.patch("/{asset_id}/state")
def patch_state(
    services: ServicesDep, viewer: ViewerDep, asset_id: int, body: StatePatch
) -> AssetOut:
    if body.private is not None:
        # needs edit from a source (or admin), never "first importer owns it" (QA A3)
        require_view(services, viewer, asset_id, Level.EDIT)
        services.repo.set_private(asset_id, body.private, viewer.user_id)
    else:
        require_view(services, viewer, asset_id)
    if body.favourite is not None or body.hidden is not None:
        services.repo.set_user_state(
            viewer.user_id, [asset_id], favourite=body.favourite, hidden=body.hidden
        )
    return asset_out(services, require_view(services, viewer, asset_id))


def _serve_webp(services: Services, view: AssetView, kind: str) -> Response:
    path = services.editor.image_for(view, kind)
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not generated yet")
    # until its preview is made, a photo's thumbnail stands in for it: never cache that one
    stand_in = kind == "preview" and view.recipe is None and view.asset.preview_path is None
    cache = "no-store" if stand_in else IMMUTABLE
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": cache})


def _image_view(services: Services, viewer: Viewer, asset_id: int) -> AssetView:
    """Thumbnails and previews also serve photos in the trash, to whoever sees them there
    (QA A10: the trash page must show what it lists). Nothing else does."""
    view = services.repo.get_view(viewer, asset_id) or services.repo.get_view(
        viewer, asset_id, trashed=True
    )
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    return view


@router.get("/{asset_id}/thumb")
def thumb(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> Response:
    return _serve_webp(services, _image_view(services, viewer, asset_id), "thumb")


@router.get("/{asset_id}/preview")
def preview(
    services: ServicesDep,
    viewer: ViewerDep,
    asset_id: int,
    edit: Annotated[Literal["none"] | None, Query()] = None,
) -> Response:
    """``?edit=none`` (v1.1): the photo without its recipe, the editor's base image."""
    view = _image_view(services, viewer, asset_id)
    if edit == "none":
        view = replace(view, recipe=None)
    return _serve_webp(services, view, "preview")


@router.get("/{asset_id}/original")
def original(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> Response:
    a = require_view(services, viewer, asset_id, Level.DOWNLOAD).asset
    path = services.store.absolute(a.library_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "original missing from the library")
    name = services.repo.first_origin_name(asset_id) or path.name
    return FileResponse(path, media_type=a.mime_type or "application/octet-stream", filename=name)
