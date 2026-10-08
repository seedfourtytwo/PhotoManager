"""Album → print (docs/contracts/api-v1.md): options, page plan, PDF and one-page previews.

Printing puts full-resolution pixels into a file, so it needs ``download`` on every photo of
the album you can see (the same rule as the ZIP export); photos hidden from you are left out,
as in the album view.
"""

import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep
from photo_assistant.api.schemas import Id
from photo_assistant.api.services import Services
from photo_assistant.app.album_printer import (
    AlbumPrintBlockedError,
    AlbumToPrint,
    Issue,
    ManualPage,
    PrintRequest,
)
from photo_assistant.domain.access import Level, Viewer
from photo_assistant.domain.errors import ForbiddenError
from photo_assistant.domain.print_layout import LAYOUTS, TRIM_SIZES
from photo_assistant.domain.print_theme import THEMES

router = APIRouter(prefix="/api", tags=["print"], dependencies=LOGGED_IN)


class TrimOut(BaseModel):
    id: str
    label: str
    width_mm: float
    height_mm: float


class ThemeOut(BaseModel):
    id: str
    label: str
    paper: str
    ink: str
    font: str


class LayoutOut(BaseModel):
    id: str
    label: str
    capacity: int


class PrintOptionsOut(BaseModel):
    trims: list[TrimOut]
    themes: list[ThemeOut]
    layouts: list[LayoutOut]


MAX_PAGE_PHOTOS = max(lay.capacity for lay in LAYOUTS.values())  # no layout holds more
MAX_PAGES = 10_000  # an album's own photo limit, at one photo a page
MAX_PAGE_TEXT = 5000  # as an album's description, the other free text that is printed
_NAME = Field(max_length=40)  # trim, theme and layout ids are short words


class PageIn(BaseModel):
    layout_id: Annotated[str, _NAME]
    asset_ids: list[Id] = Field(max_length=MAX_PAGE_PHOTOS)
    text: str = Field(default="", max_length=MAX_PAGE_TEXT)


class PrintRequestIn(BaseModel):
    trim: Annotated[str, _NAME] = "a4-landscape"
    theme: Annotated[str, _NAME] = "quiet"
    cover: bool = True
    crop_marks: bool = False
    pages: list[PageIn] | None = Field(default=None, max_length=MAX_PAGES)
    allow_low_resolution: bool = False

    def to_request(self) -> PrintRequest:
        pages = None
        if self.pages is not None:
            pages = tuple(ManualPage(p.layout_id, tuple(p.asset_ids), p.text) for p in self.pages)
        return PrintRequest(
            trim=self.trim,
            theme=self.theme,
            cover=self.cover,
            crop_marks=self.crop_marks,
            pages=pages,
            allow_low_resolution=self.allow_low_resolution,
        )


class PageOut(BaseModel):
    layout_id: str
    photos: list[int]
    text: str


class IssueOut(BaseModel):
    asset_id: int | None
    ppi: float
    level: str  # warn | block


class PlanOut(BaseModel):
    pages: list[PageOut]
    issues: list[IssueOut]
    page_count: int


def _issues(issues: tuple[Issue, ...]) -> list[IssueOut]:
    return [IssueOut(asset_id=a, ppi=round(p, 1), level=lvl) for a, p, lvl in issues]


def _album(services: Services, viewer: Viewer, album_id: int) -> AlbumToPrint:
    info = services.repo.album_info(viewer, album_id)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "album not found")
    items = services.repo.album_views(viewer, album_id)
    if any(v.level < Level.DOWNLOAD for v in items):
        raise ForbiddenError("printing needs 'download' access to every photo")
    cover = next((v for v in items if v.id == info.cover_asset_id), None)
    return AlbumToPrint(info.title, info.description, info.updated_at, items, cover)


def _file_name(title: str) -> str:
    return (re.sub(r"[^\w\- ]+", "_", title, flags=re.ASCII).strip() or "album") + ".pdf"


@router.get("/print/options")
def print_options() -> PrintOptionsOut:
    return PrintOptionsOut(
        trims=[
            TrimOut(id=t.id, label=t.label, width_mm=t.width_mm, height_mm=t.height_mm)
            for t in TRIM_SIZES.values()
        ],
        themes=[
            ThemeOut(id=t.id, label=t.label, paper=t.paper, ink=t.ink, font=t.font)
            for t in THEMES.values()
        ],
        layouts=[
            LayoutOut(id=lay.id, label=lay.label, capacity=lay.capacity) for lay in LAYOUTS.values()
        ],
    )


@router.post("/albums/{album_id}/print/plan")
def plan(services: ServicesDep, viewer: ViewerDep, album_id: int, body: PrintRequestIn) -> PlanOut:
    album = _album(services, viewer, album_id)
    planned = services.printer.plan(album, body.to_request())
    return PlanOut(
        pages=[
            PageOut(layout_id=lay, photos=list(ids), text=text) for lay, ids, text in planned.pages
        ],
        issues=_issues(planned.issues),
        page_count=planned.plan.job.page_count,
    )


@router.post("/albums/{album_id}/print")
def print_pdf(
    services: ServicesDep, viewer: ViewerDep, album_id: int, body: PrintRequestIn
) -> Response:
    album = _album(services, viewer, album_id)
    try:
        result, issues = services.printer.pdf(album, body.to_request())
    except AlbumPrintBlockedError as exc:  # its body also lists the photos: not the handler's
        content = {"detail": str(exc), "issues": [i.model_dump() for i in _issues(exc.issues)]}
        return JSONResponse(content, status_code=exc.status)
    return Response(
        result.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_file_name(album.title)}"',
            "X-Print-Warnings": str(len(issues)),
        },
    )


@router.get("/albums/{album_id}/print/preview")
def print_preview(
    services: ServicesDep,
    viewer: ViewerDep,
    album_id: int,
    page: Annotated[int, Query(description="1-based; the cover is page 1")],
    trim: str = "a4-landscape",
    theme: str = "quiet",
    cover: bool = True,
    ppi: Annotated[float, Query(ge=24, le=300)] = 96,
) -> Response:
    album = _album(services, viewer, album_id)
    req = PrintRequest(trim=trim, theme=theme, cover=cover)
    png = services.printer.preview(album, req, page, ppi)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
