"""The print port (FEATURES §6): a fully decided album goes in, PDF or PNG bytes come out.

A ``PrintJob`` carries every geometric decision already made (frames in mm, crops in
fractions), so a renderer only draws. Frames are page coordinates with the origin at the
top-left corner of the trim; a full-bleed frame starts at ``-BLEED_MM``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.print_layout import Rect, TrimSize
from photo_assistant.domain.print_theme import Theme


class PrintRenderError(RuntimeError):
    """The engine could not render the job (unreadable image, template error)."""


@dataclass(frozen=True)
class PrintSlot:
    image_path: Path  # absolute; a JPEG/PNG/WebP already oriented and edited
    pixel_w: int
    pixel_h: int
    crop: Rect  # fractions of the image
    frame: Rect  # mm, page coordinates


@dataclass(frozen=True)
class PrintPage:
    layout_id: str
    slots: tuple[PrintSlot, ...] = ()
    caption: str = ""
    text: str = ""


@dataclass(frozen=True)
class PrintCover:
    photo: PrintSlot | None = None


@dataclass(frozen=True)
class PrintJob:
    title: str
    subtitle: str
    trim: TrimSize
    theme: Theme
    pages: tuple[PrintPage, ...]
    cover: PrintCover | None = None
    crop_marks: bool = False

    @property
    def page_count(self) -> int:
        return len(self.pages) + (1 if self.cover else 0)


class PrintRenderer(Protocol):
    def render_pdf(self, job: PrintJob) -> bytes:
        """The whole album as one print-ready PDF."""
        ...

    def render_preview(self, job: PrintJob, page_number: int, ppi: float = 96) -> bytes:
        """One page (1-based, the cover is page 1 when present) as a PNG."""
        ...
