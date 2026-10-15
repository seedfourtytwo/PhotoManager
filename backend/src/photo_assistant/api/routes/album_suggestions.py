"""Suggested albums (FEATURES 5.6): the signed-in account's events, proposed as albums it keeps
or discards."""

from datetime import date

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from photo_assistant.api.deps import LOGGED_IN, MemberUser, ServicesDep, ViewerDep
from photo_assistant.api.schemas import AlbumSummary, AssetOut
from photo_assistant.app import album_suggestions
from photo_assistant.app.album_suggestions import PREVIEW

router = APIRouter(prefix="/api/album-suggestions", tags=["albums"], dependencies=LOGGED_IN)


class SuggestionOut(BaseModel):
    key: str
    title: str
    from_day: date = Field(serialization_alias="from")
    to_day: date = Field(serialization_alias="to")
    count: int
    cover: AssetOut
    items: list[AssetOut]  # its first few photos, in time order


@router.get("")
def list_suggestions(services: ServicesDep, viewer: ViewerDep) -> list[SuggestionOut]:
    found = album_suggestions.suggestions(services.repo, viewer)
    wanted = [i for s in found for i in (s.cover_id, *s.asset_ids[:PREVIEW])]
    shown = {v.id: AssetOut.of(v) for v in services.repo.views_by_ids(viewer, wanted)}
    return [
        SuggestionOut(
            key=s.key,
            title=s.title,
            from_day=s.first_day,
            to_day=s.last_day,
            count=s.count,
            cover=shown[s.cover_id],
            items=[shown[i] for i in s.asset_ids[:PREVIEW]],
        )
        for s in found
    ]


@router.post("/{key}/keep", status_code=status.HTTP_201_CREATED)
def keep(services: ServicesDep, viewer: ViewerDep, key: str, user: MemberUser) -> AlbumSummary:
    album_id = album_suggestions.keep(services.repo, viewer, key, services.clock.now())
    album = services.repo.album_info(viewer, album_id)
    assert album is not None  # just made, by this account
    return AlbumSummary.of(album)


@router.post("/{key}/discard", status_code=status.HTTP_204_NO_CONTENT)
def discard(services: ServicesDep, viewer: ViewerDep, key: str, user: MemberUser) -> Response:
    album_suggestions.discard(services.repo, viewer, key, services.clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
