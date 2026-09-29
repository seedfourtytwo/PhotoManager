"""Trash: delete (soft), list, restore, empty (contract: Trash)."""

from fastapi import APIRouter, status

from photo_assistant.api.deps import (
    ADMIN_ONLY,
    LOGGED_IN,
    ServicesDep,
    ViewerDep,
    require_views,
)
from photo_assistant.api.schemas import (
    AssetOut,
    IdsIn,
    OptionalIds,
    Purged,
    Restored,
    Trashed,
    TrashedOut,
)
from photo_assistant.domain.access import Level

router = APIRouter(prefix="/api", tags=["trash"], dependencies=LOGGED_IN)


@router.delete("/assets")
def trash_assets(services: ServicesDep, viewer: ViewerDep, body: IdsIn) -> Trashed:
    """Move photos to the trash (needs edit on every one). Sources are never touched."""
    require_views(services, viewer, body.ids, Level.EDIT)
    return Trashed(trashed=services.trash.trash(body.ids, viewer.user_id))


@router.get("/trash")
def list_trash(services: ServicesDep, viewer: ViewerDep) -> list[TrashedOut]:
    return [
        TrashedOut(**AssetOut.of(v).model_dump(), trashed_at=v.trashed_at)
        for v in services.repo.trashed_views(viewer)
        if v.trashed_at is not None
    ]


@router.post("/trash/restore")
def restore(services: ServicesDep, viewer: ViewerDep, body: IdsIn) -> Restored:
    require_views(services, viewer, body.ids, Level.EDIT, trashed=True)
    return Restored(restored=services.trash.restore(body.ids))


@router.post("/trash/empty", dependencies=ADMIN_ONLY, status_code=status.HTTP_200_OK)
def empty(services: ServicesDep, body: OptionalIds | None = None) -> Purged:
    """Remove the library copy and derivatives for good; sources are never touched."""
    ids = body.ids if body is not None else None
    return Purged(purged=services.trash.empty(ids))
