"""PrintRenderer with Typst (TECH_DECISIONS: Print), compiled in-process via the typst package.

The template only draws; this module turns a ``PrintJob`` into the template's JSON. The sheet
is the trim plus 3 mm bleed on every side (plus a slug for crop marks when asked). Only the
fonts compiled into Typst are used and the creation date is pinned, so the same job always
produces the same bytes.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import typst

from photo_assistant.domain.print_layout import BLEED_MM, TEXT_LAYOUT_ID, Rect, layout
from photo_assistant.domain.print_theme import page_geometry
from photo_assistant.ports.printing import PrintJob, PrintPage, PrintRenderError, PrintSlot

Json = dict[str, Any]  # the template's input: plain JSON values
TEMPLATE = Path(__file__).parent / "typst_templates" / "album.typ"
DEFAULT_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _rect(r: Rect) -> Json:
    return {"x": r.x, "y": r.y, "w": r.w, "h": r.h}


def _frame(slot: PrintSlot) -> Json:
    """Frame geometry plus where the whole image sits so that only the crop shows."""
    img_w, img_h = slot.frame.w / slot.crop.w, slot.frame.h / slot.crop.h
    return {
        **_rect(slot.frame),
        "path": str(slot.image_path),
        "img_w": img_w,
        "img_h": img_h,
        "dx": -slot.crop.x * img_w,
        "dy": -slot.crop.y * img_h,
    }


def _crop_marks(job: PrintJob, slug: float) -> list[list[float]]:
    """Hairlines on the trim lines, in the slug, clear of the bleed."""
    w, h = job.trim.width_mm, job.trim.height_mm
    near, far = 1.0, slug - 1.0  # distance from the sheet edge
    origin = slug + BLEED_MM
    marks: list[list[float]] = []
    for x in (origin, origin + w):
        marks += [[x, near, x, far], [x, origin * 2 + h - far, x, origin * 2 + h - near]]
    for y in (origin, origin + h):
        marks += [[near, y, far, y], [origin * 2 + w - far, y, origin * 2 + w - near, y]]
    return marks


class TypstPrintRenderer:
    SLUG_MM = 10.0  # extra paper outside the bleed, only when crop marks are requested

    def __init__(self, timestamp: datetime = DEFAULT_TIMESTAMP, template: Path = TEMPLATE) -> None:
        self._timestamp = timestamp.replace(microsecond=0)  # Typst dates have whole seconds
        self._template = template

    def render_pdf(self, job: PrintJob) -> bytes:
        return self._compile(job, "pdf")

    def render_preview(self, job: PrintJob, page_number: int, ppi: float = 96) -> bytes:
        return self._compile(self._single_page(job, page_number), "png", ppi)

    @staticmethod
    def _single_page(job: PrintJob, page_number: int) -> PrintJob:
        if not 1 <= page_number <= job.page_count:
            raise PrintRenderError(f"page {page_number} is outside 1..{job.page_count}")
        if job.cover and page_number == 1:
            return replace(job, pages=())
        index = page_number - (2 if job.cover else 1)
        return replace(job, pages=(job.pages[index],), cover=None)

    def _compile(
        self, job: PrintJob, fmt: Literal["pdf", "png"], ppi: float | None = None
    ) -> bytes:
        try:
            out = typst.compile(
                self._template,
                root=Path("/"),  # image paths are absolute
                format=fmt,
                ppi=ppi,
                sys_inputs={"job": json.dumps(self.to_template(job))},
                ignore_system_fonts=True,
                timestamp=self._timestamp,
            )
        except typst.TypstError as err:
            raise PrintRenderError(f"could not render the album: {err.message}") from err
        # Typst returns one PNG per page; a preview job has exactly one page.
        return out[0] if isinstance(out, list) else out

    def to_template(self, job: PrintJob) -> Json:
        """The template's JSON input (public for debugging and golden tests)."""
        slug = self.SLUG_MM if job.crop_marks else 0.0
        t = job.theme
        pages = [self._cover(job)] if job.cover else []
        pages += [self._page(job, p) for p in job.pages]
        return {
            "title": job.title,
            "theme": {
                "paper": t.paper,
                "ink": t.ink,
                "ink_secondary": t.ink_secondary,
                "font": t.font,
                "title_size": t.title_size_pt,
                "text_size": t.text_size_pt,
                "caption_size": t.caption_size_pt,
            },
            "sheet": self._sheet(job, slug),
            "pages": pages,
        }

    @staticmethod
    def _sheet(job: PrintJob, slug: float) -> Json:
        w, h = job.trim.width_mm, job.trim.height_mm
        paper = Rect(slug, slug, w + 2 * BLEED_MM, h + 2 * BLEED_MM)
        return {
            "width": paper.w + 2 * slug,
            "height": paper.h + 2 * slug,
            "origin": slug + BLEED_MM,
            "paper": _rect(paper),
            "marks": _crop_marks(job, slug) if job.crop_marks else [],
        }

    @staticmethod
    def _page(job: PrintJob, page: PrintPage) -> Json:
        geometry = page_geometry(job.theme, job.trim)
        content = geometry.content
        caption = None
        if page.caption and not layout(page.layout_id).bleed:
            # Same baseline on every page; aligned with the photos it describes.
            x = min((s.frame.x for s in page.slots), default=content.x)
            y = geometry.caption_baseline_mm
            caption = {"x": x, "y": y, "w": content.right - x, "text": page.caption}
        prose = None
        if page.layout_id == TEXT_LAYOUT_ID and page.text:
            prose = {**_rect(geometry.text_block), "text": page.text}
        frames = [_frame(s) for s in page.slots]
        return {"frames": frames, "caption": caption, "title": None, "prose": prose}

    @staticmethod
    def _cover(job: PrintJob) -> Json:
        geometry = page_geometry(job.theme, job.trim)
        photo = job.cover.photo if job.cover else None
        left = photo.frame.x if photo else geometry.content.x
        title = {
            "x": left,
            "y": geometry.cover_title_baseline_mm,
            "w": geometry.content.right - left,
            "text": job.title,
            "subtitle": job.subtitle,
        }
        frames = [_frame(photo)] if photo else []
        return {"frames": frames, "caption": None, "title": title, "prose": None}
