"""Downloads: one photo, or many as a streamed ZIP (contract: Downloads)."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from photo_assistant.adapters.zip_stream import zip_stream
from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep, require_view
from photo_assistant.api.filters import checked
from photo_assistant.api.schemas import DownloadRequest, Estimate
from photo_assistant.api.services import Services
from photo_assistant.app.downloads import MEDIA_TYPES, Entry, downloadable
from photo_assistant.domain.access import Level, Viewer
from photo_assistant.domain.archive_name import (
    album_zip_name,
    ascii_fallback,
    filters_zip_name,
    ids_zip_name,
)
from photo_assistant.domain.export_naming import MAX_EDGE, ExportOptions
from photo_assistant.ports.library import AssetView

router = APIRouter(prefix="/api", tags=["downloads"], dependencies=LOGGED_IN)

_FORMS = ("application/x-www-form-urlencoded", "multipart/form-data")


async def download_request(request: Request) -> DownloadRequest:
    """A JSON body, or (v1.1) a form whose field ``request`` holds that JSON: the web app posts
    a real form into a hidden frame so the browser streams the ZIP straight to disk."""
    if request.headers.get("content-type", "").startswith(_FORMS):
        raw = (await request.form()).get("request")
        if not isinstance(raw, str):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "the form needs a 'request' field (JSON)"
            )
    else:
        raw = (await request.body()).decode("utf-8", "replace")
    try:
        return DownloadRequest.model_validate_json(raw)
    except ValidationError as exc:
        detail = "; ".join(e["msg"] for e in exc.errors(include_url=False))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from exc


DownloadBody = Annotated[DownloadRequest, Depends(download_request)]
_BODY_SCHEMA = {
    "requestBody": {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/DownloadRequest"}},
            "application/x-www-form-urlencoded": {
                "schema": {"type": "object", "properties": {"request": {"type": "string"}}}
            },
        },
        "required": True,
    }
}


@dataclass(frozen=True, slots=True)
class _Scope:
    views: list[AssetView]  # the photos asked for that you can see
    asked: int  # how many were asked for
    zip_name: str  # named after the album, the filters or the count (v1.3)


def _scope(services: Services, viewer: Viewer, body: DownloadRequest) -> _Scope:
    given = [s is not None for s in (body.ids, body.album_id, body.filters)]
    if sum(given) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "give exactly one of ids, album_id or filters"
        )
    if body.ids is not None:
        asked = len(set(body.ids))
        return _Scope(services.repo.views_by_ids(viewer, body.ids), asked, ids_zip_name(asked))
    if body.album_id is not None:
        album = services.repo.album_info(viewer, body.album_id)
        if album is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "album not found")
        views = services.repo.album_views(viewer, body.album_id)
        return _Scope(views, len(views), album_zip_name(album.title))
    assert body.filters is not None
    asset_filter = checked(body.filters.to_filter())
    views = services.repo.list_all_views(viewer, asset_filter)
    return _Scope(views, len(views), filters_zip_name(asset_filter))


def _entries(
    services: Services, viewer: Viewer, body: DownloadRequest
) -> tuple[list[Entry], _Scope, ExportOptions]:
    scope = _scope(services, viewer, body)
    allowed = downloadable(scope.views)
    options = body.options()
    names = [services.repo.first_origin_name(v.id) or "photo" for v in allowed]
    return services.downloads.plan(allowed, names, options), scope, options


@router.post("/downloads/estimate")
def estimate(services: ServicesDep, viewer: ViewerDep, body: DownloadRequest) -> Estimate:
    entries, _, options = _entries(services, viewer, body)
    views = [e.view for e in entries]
    return Estimate(count=len(views), bytes=services.downloads.estimate(views, options))


@router.post("/downloads", openapi_extra=_BODY_SCHEMA)
def download_zip(services: ServicesDep, viewer: ViewerDep, body: DownloadBody) -> StreamingResponse:
    entries, scope, options = _entries(services, viewer, body)
    files = ((e.name, services.downloads.content(e.view, options)) for e in entries)
    return StreamingResponse(
        zip_stream(files),
        media_type="application/zip",
        headers={
            "Content-Disposition": _attachment(scope.zip_name),
            "X-Skipped": str(scope.asked - len(entries)),
        },
    )


@router.get("/assets/{asset_id}/download")
def download_one(
    services: ServicesDep,
    viewer: ViewerDep,
    asset_id: int,
    fmt: Annotated[str, Query(alias="format")] = "original",
    quality: Annotated[int, Query(ge=1, le=100)] = 90,
    max_edge: Annotated[int | None, Query(ge=1, le=MAX_EDGE)] = None,
    strip_location: bool = False,
) -> StreamingResponse:
    view = require_view(services, viewer, asset_id, Level.DOWNLOAD)
    options = ExportOptions(  # OptionsError: 422
        format=fmt, quality=quality, max_edge=max_edge, strip_location=strip_location
    )
    name = services.repo.first_origin_name(asset_id) or "photo"
    entry = services.downloads.plan([view], [name], options)[0]
    out_format = services.downloads.output_format(view, options)
    media = MEDIA_TYPES.get(out_format, view.asset.mime_type or "application/octet-stream")
    content: Iterator[bytes] = services.downloads.content(view, options)
    return StreamingResponse(
        content,
        media_type=media,
        headers={"Content-Disposition": _attachment(entry.name)},
    )


def _attachment(name: str) -> str:
    """RFC 6266: ``filename*`` carries the real UTF-8 name ('beach day 🌊.jpg'), ``filename``
    an ASCII stand-in for clients that ignore it."""
    return (
        f"attachment; filename=\"{ascii_fallback(name)}\"; filename*=UTF-8''{quote(name, safe='')}"
    )
