"""Downloads: one photo, or many as a streamed ZIP (contract: Downloads)."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from photo_assistant.adapters.zip_stream import zip_stream
from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep, require_view
from photo_assistant.api.filters import checked
from photo_assistant.api.schemas import DownloadRequest, Estimate
from photo_assistant.api.services import Services
from photo_assistant.app.downloads import MEDIA_TYPES, Entry, downloadable
from photo_assistant.domain.access import Level, Viewer
from photo_assistant.domain.export_naming import ExportOptions, OptionsError
from photo_assistant.ports.library import AssetView

router = APIRouter(prefix="/api", tags=["downloads"], dependencies=LOGGED_IN)


def _scope(
    services: Services, viewer: Viewer, body: DownloadRequest
) -> tuple[list[AssetView], int]:
    """The photos asked for that you can see, and how many were asked for in total."""
    given = [s is not None for s in (body.ids, body.album_id, body.filters)]
    if sum(given) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "give exactly one of ids, album_id or filters"
        )
    if body.ids is not None:
        return services.repo.views_by_ids(viewer, body.ids), len(set(body.ids))
    if body.album_id is not None:
        if services.repo.album_info(viewer, body.album_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "album not found")
        views = services.repo.album_views(viewer, body.album_id)
        return views, len(views)
    assert body.filters is not None
    views = services.repo.list_all_views(viewer, checked(body.filters.to_filter()))
    return views, len(views)


def _entries(
    services: Services, viewer: Viewer, body: DownloadRequest
) -> tuple[list[Entry], int, ExportOptions]:
    views, asked = _scope(services, viewer, body)
    allowed = downloadable(views)
    options = body.options()
    names = [services.repo.first_origin_name(v.id) or "photo" for v in allowed]
    return services.downloads.plan(allowed, names, options), asked - len(allowed), options


@router.post("/downloads/estimate")
def estimate(services: ServicesDep, viewer: ViewerDep, body: DownloadRequest) -> Estimate:
    entries, _, options = _entries(services, viewer, body)
    views = [e.view for e in entries]
    return Estimate(count=len(views), bytes=services.downloads.estimate(views, options))


@router.post("/downloads")
def download_zip(
    services: ServicesDep, viewer: ViewerDep, body: DownloadRequest
) -> StreamingResponse:
    entries, skipped, options = _entries(services, viewer, body)
    files = ((e.name, services.downloads.content(e.view, options)) for e in entries)
    return StreamingResponse(
        zip_stream(files),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="photos.zip"',
            "X-Skipped": str(skipped),
        },
    )


@router.get("/assets/{asset_id}/download")
def download_one(
    services: ServicesDep,
    viewer: ViewerDep,
    asset_id: int,
    fmt: Annotated[str, Query(alias="format")] = "original",
    quality: Annotated[int, Query(ge=1, le=100)] = 90,
    max_edge: Annotated[int | None, Query(ge=1)] = None,
    strip_location: bool = False,
) -> StreamingResponse:
    view = require_view(services, viewer, asset_id, Level.DOWNLOAD)
    try:
        options = ExportOptions(
            format=fmt, quality=quality, max_edge=max_edge, strip_location=strip_location
        )
    except OptionsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
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
    """RFC 6266 with a UTF-8 fallback, so names like 'beach day 🌊.jpg' survive."""
    from urllib.parse import quote

    ascii_name = name.encode("ascii", "replace").decode().replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
