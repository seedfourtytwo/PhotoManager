"""Albums: owner, members with roles, ordered photos (contract: Albums)."""

from fastapi import APIRouter, HTTPException, Response, status

from photo_assistant.api.deps import LOGGED_IN, MemberUser, ServicesDep, ViewerDep
from photo_assistant.api.schemas import (
    AlbumDetail,
    AlbumIn,
    AlbumItemsIn,
    AlbumItemsOut,
    AlbumOrder,
    AlbumPatch,
    AlbumSummary,
    AssetOut,
    Counted,
    Member,
)
from photo_assistant.api.services import Services
from photo_assistant.domain.access import AlbumRole, Viewer, can_edit_album
from photo_assistant.domain.errors import ForbiddenError
from photo_assistant.ports.library import AlbumInfo

router = APIRouter(prefix="/api/albums", tags=["albums"], dependencies=LOGGED_IN)


def _album(services: Services, viewer: Viewer, album_id: int) -> AlbumInfo:
    album = services.repo.album_info(viewer, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "album not found")
    return album


def _editable(services: Services, viewer: Viewer, album_id: int) -> AlbumInfo:
    album = _album(services, viewer, album_id)
    if not can_edit_album(album.role, viewer.role):
        raise ForbiddenError("you can look at this album, not change it")
    return album


def _owned(services: Services, viewer: Viewer, album_id: int) -> AlbumInfo:
    album = _album(services, viewer, album_id)
    if album.role is not AlbumRole.OWNER and not viewer.is_admin:
        raise ForbiddenError("only the album's owner can do this")
    return album


def _visible_ids(services: Services, viewer: Viewer, ids: list[int]) -> list[int]:
    """Only photos you can see go into an album."""
    return [v.id for v in services.repo.views_by_ids(viewer, ids)]


@router.get("")
def list_albums(services: ServicesDep, viewer: ViewerDep) -> list[AlbumSummary]:
    return [AlbumSummary.of(a) for a in services.repo.list_albums(viewer)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_album(
    services: ServicesDep, viewer: ViewerDep, body: AlbumIn, user: MemberUser
) -> AlbumSummary:
    now = services.clock.now()
    album_id = services.repo.create_album(viewer.user_id, body.title, body.description, now)
    ids = _visible_ids(services, viewer, body.asset_ids)
    if ids:
        services.repo.add_album_items(album_id, ids, None, now)
    return AlbumSummary.of(_album(services, viewer, album_id))


@router.get("/{album_id}")
def get_album(services: ServicesDep, viewer: ViewerDep, album_id: int) -> AlbumDetail:
    album = _album(services, viewer, album_id)
    items = [AssetOut.of(v) for v in services.repo.album_views(viewer, album_id)]
    return AlbumDetail(**AlbumSummary.of(album).model_dump(), items=items)


@router.patch("/{album_id}")
def patch_album(
    services: ServicesDep, viewer: ViewerDep, album_id: int, body: AlbumPatch
) -> AlbumSummary:
    _editable(services, viewer, album_id)
    cover = body.cover_asset_id
    if cover is not None and cover not in {
        v.id for v in services.repo.album_views(viewer, album_id)
    }:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "the cover must be a photo in this album"
        )
    services.repo.update_album(
        album_id,
        services.clock.now(),
        title=body.title,
        description=body.description,
        cover_asset_id=cover,
    )
    return AlbumSummary.of(_album(services, viewer, album_id))


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_album(services: ServicesDep, viewer: ViewerDep, album_id: int) -> Response:
    """Removes the album only; its photos stay in the library."""
    _owned(services, viewer, album_id)
    services.repo.delete_album(album_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{album_id}/items")
def add_items(
    services: ServicesDep, viewer: ViewerDep, album_id: int, body: AlbumItemsIn
) -> Counted:
    """``position`` counts the photos *you* see in the album (the index the web shows)."""
    _editable(services, viewer, album_id)
    ids = _visible_ids(services, viewer, body.asset_ids)
    before = None
    if body.position is not None:
        shown = [v.id for v in services.repo.album_views(viewer, album_id)]
        before = shown[body.position] if body.position < len(shown) else None
    added = services.repo.add_album_items(album_id, ids, before, services.clock.now())
    return Counted(count=added)


@router.delete("/{album_id}/items")
def remove_items(
    services: ServicesDep, viewer: ViewerDep, album_id: int, body: AlbumItemsOut
) -> Counted:
    _editable(services, viewer, album_id)
    ids = _visible_ids(services, viewer, body.asset_ids)
    removed = services.repo.remove_album_items(album_id, ids, services.clock.now())
    return Counted(count=removed)


@router.put("/{album_id}/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder(services: ServicesDep, viewer: ViewerDep, album_id: int, body: AlbumOrder) -> Response:
    _editable(services, viewer, album_id)
    if set(_visible_ids(services, viewer, body.asset_ids)) != set(body.asset_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown photos in the order")
    services.repo.reorder_album(album_id, body.asset_ids, services.clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{album_id}/members")
def get_members(services: ServicesDep, viewer: ViewerDep, album_id: int) -> list[Member]:
    _album(services, viewer, album_id)
    return [
        Member(user_id=u, role=r.value)  # type: ignore[arg-type]  # viewer | editor
        for u, r in services.repo.album_members(album_id)
    ]


@router.put("/{album_id}/members")
def put_members(
    services: ServicesDep, viewer: ViewerDep, album_id: int, body: list[Member]
) -> list[Member]:
    album = _owned(services, viewer, album_id)
    if any(m.user_id == album.owner_id for m in body):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "the owner is not listed as a member"
        )
    members = [(m.user_id, AlbumRole(m.role)) for m in body]
    services.repo.set_album_members(album_id, members, services.clock.now())  # unknown: 422
    return get_members(services, viewer, album_id)
