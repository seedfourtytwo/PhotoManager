"""Print geometry for albums (FEATURES §5.4, §6): trim sizes, layout templates, crops, ppi.

Everything here is pure arithmetic in millimetres (page coordinates, origin at the top-left
corner of the *trim*) or in fractions (slots of a layout, crops of an image). The renderer
only draws what these functions decide, so every layout rule is unit-testable.

Invariants (checked by property tests):
- ``auto_layout`` places every photo exactly once, in the given order.
- ``cover_crop`` returns a crop inside the image with exactly the frame's aspect ratio.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from photo_assistant.domain.errors import InvalidError

MM_PER_INCH = 25.4
BLEED_MM = 3.0
SAFE_MARGIN_MM = 5.0
WARN_BELOW_PPI = 200.0
BLOCK_BELOW_PPI = 150.0


class UnknownTrimSizeError(InvalidError):
    """A trim size id that is not one of the presets."""


class UnknownLayoutError(InvalidError):
    """A layout id that is not one of the templates."""


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle: in mm (frames) or in fractions 0..1 (slots, crops)."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def aspect(self) -> float:
        return self.w / self.h

    def inset(self, d: float) -> "Rect":
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)

    def overlaps(self, other: "Rect") -> bool:
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )


FULL = Rect(0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class TrimSize:
    id: str
    label: str
    width_mm: float
    height_mm: float

    @property
    def aspect(self) -> float:
        return self.width_mm / self.height_mm


TRIM_SIZES: dict[str, TrimSize] = {
    t.id: t
    for t in (
        TrimSize("a4-portrait", "A4 portrait", 210.0, 297.0),
        TrimSize("a4-landscape", "A4 landscape", 297.0, 210.0),
        TrimSize("a5-portrait", "A5 portrait", 148.0, 210.0),
        TrimSize("a5-landscape", "A5 landscape", 210.0, 148.0),
        TrimSize("square-20", "Square 20 cm", 200.0, 200.0),
        TrimSize("us-letter", "US Letter", 215.9, 279.4),
    )
}


def trim_size(trim_id: str) -> TrimSize:
    try:
        return TRIM_SIZES[trim_id]
    except KeyError:
        raise UnknownTrimSizeError(f"unknown trim size: {trim_id!r}") from None


class Fit(StrEnum):
    COVER = "cover"  # fill the slot, crop the overflow (album frames)
    CONTAIN = "contain"  # justify the photos along an axis inside the slots: never crops


class Axis(StrEnum):
    ROW = "row"  # contained photos share one height
    COLUMN = "column"  # contained photos share one width


@dataclass(frozen=True)
class Layout:
    """A page template. Slots are fractions of the photo area, in reading order."""

    id: str
    label: str
    slots: tuple[Rect, ...]
    fit: Fit = Fit.COVER
    axis: Axis = Axis.ROW
    bleed: bool = False  # the single slot covers the whole page up to the bleed edge

    @property
    def capacity(self) -> int:
        return len(self.slots)


TEXT_LAYOUT_ID = "text"
_THIRD = 1 / 3
_HERO = 0.62

LAYOUTS: dict[str, Layout] = {
    lay.id: lay
    for lay in (
        Layout("full-bleed", "Full bleed", (FULL,), bleed=True),
        Layout("single", "Single with margin", (FULL,), fit=Fit.CONTAIN),
        Layout(
            "two-side",
            "Two side by side",
            (Rect(0, 0, 0.5, 1), Rect(0.5, 0, 0.5, 1)),
            fit=Fit.CONTAIN,
        ),
        Layout(
            "two-stacked",
            "Two stacked",
            (Rect(0, 0, 1, 0.5), Rect(0, 0.5, 1, 0.5)),
            fit=Fit.CONTAIN,
            axis=Axis.COLUMN,
        ),
        Layout(
            "three-grid",
            "Three in a row",
            tuple(Rect(i * _THIRD, 0, _THIRD, 1) for i in range(3)),
        ),
        Layout(
            "hero-two",
            "Hero and two below",
            (
                Rect(0, 0, 1, _HERO),
                Rect(0, _HERO, 0.5, 1 - _HERO),
                Rect(0.5, _HERO, 0.5, 1 - _HERO),
            ),
        ),
        Layout(
            "hero-two-side",
            "Hero and two beside",
            (
                Rect(0, 0, _HERO, 1),
                Rect(_HERO, 0, 1 - _HERO, 0.5),
                Rect(_HERO, 0.5, 1 - _HERO, 0.5),
            ),
        ),
        Layout(
            "four-grid",
            "Four in a grid",
            tuple(Rect(c * 0.5, r * 0.5, 0.5, 0.5) for r in range(2) for c in range(2)),
        ),
        Layout(TEXT_LAYOUT_ID, "Text page", ()),
    )
}

# The cover is not a page template users pick: photo above, title on its own baseline below.
COVER_LAYOUT = Layout("cover", "Cover", (Rect(0, 0, 1, 0.72),), fit=Fit.CONTAIN)
_COVER_TITLE_AT = 0.86
_TEXT_TOP_AT = 0.28
_TEXT_MEASURE_MM = 110.0  # ~65 characters of 11 pt serif: a comfortable line length
_CAPTION_BASELINE_AT = 0.62  # of the caption band, from its top


def layout(layout_id: str) -> Layout:
    try:
        return LAYOUTS[layout_id]
    except KeyError:
        raise UnknownLayoutError(f"unknown layout: {layout_id!r}") from None


@dataclass(frozen=True)
class PageGeometry:
    """Where things go on one trim size, for one theme's margins."""

    trim: TrimSize
    margin_mm: float
    gutter_mm: float
    caption_band_mm: float

    @property
    def page(self) -> Rect:
        return Rect(0.0, 0.0, self.trim.width_mm, self.trim.height_mm)

    @property
    def content(self) -> Rect:
        return self.page.inset(max(self.margin_mm, SAFE_MARGIN_MM))

    @property
    def photo_area(self) -> Rect:
        c = self.content
        return Rect(c.x, c.y, c.w, c.h - self.caption_band_mm)

    @property
    def caption_baseline_mm(self) -> float:
        """One baseline for every caption in the album."""
        return self.photo_area.bottom + self.caption_band_mm * _CAPTION_BASELINE_AT

    @property
    def cover_title_baseline_mm(self) -> float:
        area = self.photo_area
        return area.y + area.h * _COVER_TITLE_AT

    @property
    def text_block(self) -> Rect:
        c = self.content
        width = min(_TEXT_MEASURE_MM, c.w * 0.7)
        top = c.y + c.h * _TEXT_TOP_AT
        return Rect(c.x + (c.w - width) / 2, top, width, c.bottom - top)

    def slot_frames(self, lay: Layout) -> tuple[Rect, ...]:
        """Slot rectangles in mm; gutters only between photos, never at the edges."""
        if lay.bleed:
            return tuple(self.page.inset(-BLEED_MM) for _ in lay.slots)
        return tuple(self._frame(slot) for slot in lay.slots)

    def _frame(self, slot: Rect) -> Rect:
        area, half = self.photo_area, self.gutter_mm / 2
        x0 = area.x + slot.x * area.w + (half if slot.x > 0 else 0.0)
        y0 = area.y + slot.y * area.h + (half if slot.y > 0 else 0.0)
        x1 = area.x + slot.right * area.w - (half if slot.right < 1 - 1e-9 else 0.0)
        y1 = area.y + slot.bottom * area.h - (half if slot.bottom < 1 - 1e-9 else 0.0)
        return Rect(x0, y0, x1 - x0, y1 - y0)


# --- crops -------------------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def cover_crop(
    image_aspect: float, frame_aspect: float, focal: tuple[float, float] = (0.5, 0.5)
) -> Rect:
    """The largest part of the image with the frame's aspect, centred on the focal point."""
    fx, fy = focal
    if image_aspect > frame_aspect:
        w = frame_aspect / image_aspect
        return Rect(_clamp(fx - w / 2, 0.0, 1.0 - w), 0.0, w, 1.0)
    h = image_aspect / frame_aspect
    return Rect(0.0, _clamp(fy - h / 2, 0.0, 1.0 - h), 1.0, h)


def contain_frame(image_aspect: float, slot: Rect) -> Rect:
    """The largest frame with the image's aspect that fits in the slot, centred: the
    "contain" rule the Typst template applies (kept as the tests' oracle for it)."""
    if image_aspect > slot.aspect:
        h = slot.w / image_aspect
        return Rect(slot.x, slot.y + (slot.h - h) / 2, slot.w, h)
    w = slot.h * image_aspect
    return Rect(slot.x + (slot.w - w) / 2, slot.y, w, slot.h)


@dataclass(frozen=True)
class Placement:
    frame: Rect  # mm, page coordinates
    crop: Rect  # fractions of the image


def _bounds(frames: Sequence[Rect]) -> Rect:
    x0, y0 = min(f.x for f in frames), min(f.y for f in frames)
    x1, y1 = max(f.right for f in frames), max(f.bottom for f in frames)
    return Rect(x0, y0, x1 - x0, y1 - y0)


def _justify_row(area: Rect, aspects: Sequence[float], gutter: float) -> list[Rect]:
    """Photos side by side at one shared height, as large as fits, centred in the area."""
    gaps = gutter * (len(aspects) - 1)
    height = min(area.h, (area.w - gaps) / sum(aspects))
    x = area.x + (area.w - height * sum(aspects) - gaps) / 2
    y = area.y + (area.h - height) / 2
    frames = []
    for aspect in aspects:
        frames.append(Rect(x, y, height * aspect, height))
        x += height * aspect + gutter
    return frames


def _transpose(r: Rect) -> Rect:
    return Rect(r.y, r.x, r.h, r.w)


def _justify(lay: Layout, area: Rect, aspects: Sequence[float], gutter: float) -> list[Rect]:
    if lay.axis is Axis.ROW:
        return _justify_row(area, aspects, gutter)
    # A column is a row of the transposed page.
    flipped = _justify_row(_transpose(area), [1 / a for a in aspects], gutter)
    return [_transpose(f) for f in flipped]


def place_page(
    lay: Layout,
    geometry: PageGeometry,
    aspects: Sequence[float],
    focals: Sequence[tuple[float, float]] | None = None,
) -> tuple[Placement, ...]:
    """Frames (mm) and crops for the photos of one page, in slot order."""
    if len(aspects) != lay.capacity:
        raise ValueError(f"layout {lay.id!r} holds {lay.capacity} photo(s), got {len(aspects)}")
    slots = geometry.slot_frames(lay)
    if lay.fit is Fit.CONTAIN:
        frames = _justify(lay, _bounds(slots), aspects, geometry.gutter_mm)
        return tuple(Placement(f, FULL) for f in frames)
    focal_points = focals or [(0.5, 0.5)] * len(aspects)
    return tuple(
        Placement(slot, cover_crop(aspect, slot.aspect, focal))
        for slot, aspect, focal in zip(slots, aspects, focal_points, strict=True)
    )


# --- resolution --------------------------------------------------------------------------------


class Resolution(StrEnum):
    OK = "ok"
    WARN = "warn"  # visibly soft in print
    BLOCK = "block"  # too soft to print


def effective_ppi(pixel_w: int, pixel_h: int, crop: Rect, frame: Rect) -> float:
    """Pixels per inch the photo will print at: the cropped pixels over the frame size."""
    across = pixel_w * crop.w / (frame.w / MM_PER_INCH)
    down = pixel_h * crop.h / (frame.h / MM_PER_INCH)
    return min(across, down)


def check_resolution(ppi: float) -> Resolution:
    if ppi < BLOCK_BELOW_PPI:
        return Resolution.BLOCK
    if ppi < WARN_BELOW_PPI:
        return Resolution.WARN
    return Resolution.OK


# --- auto layout -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """One page of an album: a layout and the indices of the photos in its slots."""

    layout_id: str
    photos: tuple[int, ...]
    text: str = ""


# Costs are in "pages": cropping a quarter of a photo away costs about as much as a new page.
_PAGE_COST = 1.5
_CROP_WEIGHT = 4.0
_SPACE_WEIGHT = 1.0  # empty paper around a contained photo is cheaper than a lost edge
_REPEAT_PENALTY = 1.5  # the same layout twice in a row reads monotonous
_MAX_CROP_LOSS = 0.3  # never cut away more than this in an automatic layout
_Best = tuple[float, int, str]  # cost, start of last page, layout before it
_PHOTO_LAYOUTS = tuple(lay for lay in LAYOUTS.values() if lay.capacity > 0)


def _page_cost(lay: Layout, geometry: PageGeometry, photos: Sequence[float]) -> float:
    placed = place_page(lay, geometry, photos)
    if lay.fit is Fit.CONTAIN:
        used = sum(p.frame.w * p.frame.h for p in placed)
        bounds = _bounds(geometry.slot_frames(lay))
        waste = 1.0 - used / (bounds.w * bounds.h)
        return _PAGE_COST + _SPACE_WEIGHT * waste * len(photos)
    losses = [1.0 - p.crop.w * p.crop.h for p in placed]
    if max(losses) > _MAX_CROP_LOSS:
        return math.inf
    return _PAGE_COST + _CROP_WEIGHT * sum(losses)


def _extend(
    best: list[dict[str, _Best]],
    start: int,
    aspects: Sequence[float],
    geometry: PageGeometry,
) -> None:
    for last, (cost, _, _) in best[start].items():
        for lay in _PHOTO_LAYOUTS:
            end = start + lay.capacity
            if end > len(aspects):
                continue
            repeat = _REPEAT_PENALTY if lay.id == last else 0.0
            total = cost + repeat + _page_cost(lay, geometry, aspects[start:end])
            if total < best[end].get(lay.id, (math.inf, 0, ""))[0]:
                best[end][lay.id] = (total, start, last)


def _backtrack(best: list[dict[str, _Best]]) -> list[Page]:
    pages: list[Page] = []
    end = len(best) - 1
    layout_id = min(best[end], key=lambda k: best[end][k][0])
    while end > 0:
        _, start, previous = best[end][layout_id]
        pages.append(Page(layout_id, tuple(range(start, end))))
        end, layout_id = start, previous
    return pages[::-1]


def auto_layout(aspects: Sequence[float], geometry: PageGeometry) -> list[Page]:
    """Group photos (by aspect ratio, in order) into pages, minimising crop and monotony.

    Dynamic programming over the sequence: the state is (photos placed, last layout), so the
    rhythm penalty is exact and the result is the cheapest album, not a greedy guess.
    """
    if not aspects:
        return []
    best: list[dict[str, _Best]] = [{} for _ in range(len(aspects) + 1)]
    best[0][""] = (0.0, 0, "")
    for start in range(len(aspects)):
        _extend(best, start, aspects, geometry)
    return _backtrack(best)
