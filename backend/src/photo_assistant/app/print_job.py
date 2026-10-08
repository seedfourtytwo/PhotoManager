"""Print an album (FEATURES §6): ordered photos + options → print job → PDF and warnings.

Pure orchestration: layout and crop decisions come from the domain, drawing from the
``PrintRenderer`` port. Resolution is checked before anything is rendered, so a blocked
album fails fast instead of after a long compile.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.print_layout import (
    COVER_LAYOUT,
    Layout,
    Page,
    PageGeometry,
    Resolution,
    auto_layout,
    check_resolution,
    effective_ppi,
    layout,
    place_page,
    trim_size,
)
from photo_assistant.domain.print_theme import page_geometry, theme
from photo_assistant.ports.printing import (
    PrintCover,
    PrintJob,
    PrintPage,
    PrintRenderer,
    PrintSlot,
)

CAPTION_SEPARATOR = " · "


class InvalidPagesError(InvalidError):
    """Manual pages that don't fit their layouts or the album's photos."""


class EmptyAlbumError(InvalidError):
    """No photos and no cover: there is nothing to print."""


@dataclass(frozen=True)
class PrintPhoto:
    image_path: Path  # absolute path of a print-ready rendition (oriented, edits applied)
    pixel_w: int
    pixel_h: int
    caption: str = ""
    focal: tuple[float, float] = (0.5, 0.5)

    @property
    def aspect(self) -> float:
        return self.pixel_w / self.pixel_h


@dataclass(frozen=True)
class PrintOptions:
    title: str
    subtitle: str = ""
    trim: str = "a4-landscape"
    theme: str = "quiet"
    cover: bool = True
    cover_photo: PrintPhoto | None = None
    crop_marks: bool = False
    pages: tuple[Page, ...] | None = None  # manual layout; None = automatic
    allow_low_resolution: bool = False


@dataclass(frozen=True)
class ResolutionIssue:
    photo: int | None  # index in the album; None for the cover photo
    image_path: Path
    ppi: float
    level: Resolution


class PrintBlockedError(InvalidError):
    """At least one photo would print below the blocking resolution."""

    def __init__(self, issues: tuple[ResolutionIssue, ...]) -> None:
        super().__init__(f"{len(issues)} photo(s) are too small to print at this size")
        self.issues = issues


@dataclass(frozen=True)
class PrintPlan:
    job: PrintJob
    issues: tuple[ResolutionIssue, ...]

    @property
    def blocked(self) -> bool:
        return any(i.level is Resolution.BLOCK for i in self.issues)


@dataclass(frozen=True)
class PrintResult:
    pdf: bytes
    issues: tuple[ResolutionIssue, ...]
    page_count: int


def _place(
    photos: Sequence[PrintPhoto], lay: Layout, geometry: PageGeometry
) -> tuple[PrintSlot, ...]:
    aspects = [p.aspect for p in photos]
    placed = place_page(lay, geometry, aspects, [p.focal for p in photos])
    return tuple(
        PrintSlot(p.image_path, p.pixel_w, p.pixel_h, where.crop, where.frame)
        for p, where in zip(photos, placed, strict=True)
    )


def _validate(pages: Sequence[Page], photo_count: int) -> None:
    for page in pages:
        lay = layout(page.layout_id)
        if len(page.photos) != lay.capacity:
            msg = f"layout {lay.id!r} holds {lay.capacity} photo(s), got {len(page.photos)}"
            raise InvalidPagesError(msg)
        if any(not 0 <= i < photo_count for i in page.photos):
            raise InvalidPagesError(f"page refers to a photo outside the album: {page.photos}")


def _print_page(page: Page, photos: Sequence[PrintPhoto], geometry: PageGeometry) -> PrintPage:
    lay = layout(page.layout_id)
    slots = _place([photos[i] for i in page.photos], lay, geometry)
    captions = [photos[i].caption for i in page.photos if photos[i].caption]
    return PrintPage(lay.id, slots, CAPTION_SEPARATOR.join(captions), page.text)


def _cover(options: PrintOptions, geometry: PageGeometry) -> PrintCover | None:
    if not options.cover:
        return None
    if options.cover_photo is None:
        return PrintCover()
    return PrintCover(_place([options.cover_photo], COVER_LAYOUT, geometry)[0])


def _issue(photo: int | None, slot: PrintSlot) -> ResolutionIssue:
    ppi = effective_ppi(slot.pixel_w, slot.pixel_h, slot.crop, slot.frame)
    return ResolutionIssue(photo, slot.image_path, ppi, check_resolution(ppi))


def _issues(job: PrintJob, pages: Sequence[Page]) -> tuple[ResolutionIssue, ...]:
    checked = [
        _issue(index, slot)
        for page, printed in zip(pages, job.pages, strict=True)
        for index, slot in zip(page.photos, printed.slots, strict=True)
    ]
    if job.cover and job.cover.photo:
        checked.insert(0, _issue(None, job.cover.photo))
    return tuple(i for i in checked if i.level is not Resolution.OK)


def plan_print(photos: Sequence[PrintPhoto], options: PrintOptions) -> PrintPlan:
    """Decide every page, frame and crop; report photos that would print soft."""
    if not photos and not options.cover:
        raise EmptyAlbumError("the album has no photos and no cover")
    trim, look = trim_size(options.trim), theme(options.theme)
    geometry = page_geometry(look, trim)
    pages = options.pages
    if pages is None:
        pages = tuple(auto_layout([p.aspect for p in photos], geometry))
    _validate(pages, len(photos))
    job = PrintJob(
        title=options.title,
        subtitle=options.subtitle,
        trim=trim,
        theme=look,
        pages=tuple(_print_page(p, photos, geometry) for p in pages),
        cover=_cover(options, geometry),
        crop_marks=options.crop_marks,
    )
    return PrintPlan(job, _issues(job, pages))


def print_album(
    photos: Sequence[PrintPhoto], options: PrintOptions, renderer: PrintRenderer
) -> PrintResult:
    plan = plan_print(photos, options)
    if plan.blocked and not options.allow_low_resolution:
        raise PrintBlockedError(plan.issues)
    return PrintResult(renderer.render_pdf(plan.job), plan.issues, plan.job.page_count)


def preview_page(
    photos: Sequence[PrintPhoto],
    options: PrintOptions,
    renderer: PrintRenderer,
    page_number: int,
    ppi: float = 96,
) -> bytes:
    """One page as PNG, for the page editor; soft photos are shown, not blocked."""
    job = plan_print(photos, options).job
    if not 1 <= page_number <= job.page_count:
        raise InvalidPagesError(f"page {page_number} is outside 1..{job.page_count}")
    return renderer.render_preview(job, page_number, ppi)
