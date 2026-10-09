"""The look of one account: a sheet of named values, never CSS (docs/adr/0001).

A look is a theme, a mode, a few range-limited dials and a few switches. This module is the
one place that says which fields exist and what they may hold; ``docs/contracts/api-v1.md``
and ``web/src/lib/look/sheet.ts`` mirror it. Standard library only, and nothing from the rest
of the package, so it can be lifted into another project as it is.

Two ways in, on purpose:

- ``parse_look`` is strict, for a sheet someone sends: an unknown field, a value of the wrong
  kind or an unknown choice is refused (``LookError`` names the field); a number outside its
  range is clamped.
- ``read_look`` is forgiving, for what is stored: a field ``parse_look`` would refuse reads as
  its default and the rest of the sheet stays (a theme that was removed later must not cost
  the account its other choices); nothing, or something that is no sheet at all, reads as the
  defaults. So a look can never make the app unusable.

Numbers follow one rule on both sides (``docs/contracts/look-cases.json`` is the table both
test suites run): clamp first, however far outside the number is, then round a half up.
"""

import contextlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum


class Theme(StrEnum):
    SAFELIGHT = "safelight"
    ALBUM = "album"


class Mode(StrEnum):
    SYSTEM = "system"  # follow the device
    DARK = "dark"
    LIGHT = "light"


class ThumbSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class StartPage(StrEnum):
    TODAY = "today"
    LIBRARY = "library"


class CollectionsRow(StrEnum):
    PEOPLE = "people"
    PLACES = "places"
    ALBUMS = "albums"


# Dials: the lowest and highest value each may take; anything beyond is pulled back in.
ACCENT_HUE = (0, 360)  # degrees
CORNERS = (0, 22)  # px
PHOTO_GAP = (0, 8)  # px
TEXT_SCALE = (0.9, 1.25)


@dataclass(frozen=True, slots=True)
class Look:
    theme: Theme = Theme.SAFELIGHT
    mode: Mode = Mode.DARK
    # None on these three: whatever the theme itself says
    accent_hue: int | None = None
    corners: int | None = None
    photo_gap: int | None = None
    text_scale: float = 1.0
    thumb_size: ThumbSize = ThumbSize.MEDIUM
    show_today: bool = True
    start_page: StartPage = StartPage.TODAY
    collections_rows: tuple[CollectionsRow, ...] = tuple(CollectionsRow)
    dock_labels: bool = True


DEFAULT_LOOK = Look()


class LookError(ValueError):
    """A sheet that cannot be a look; the message names the field and what it may hold."""


def _number(field: str, value: object, bounds: tuple[float, float]) -> float:
    low, high = bounds
    # bool is an int to Python, but on a sheet `true` is not a number. Only a float can be
    # NaN; an infinite one, or an int too large for any float, is just far outside the range.
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or (isinstance(value, float) and math.isnan(value))
    ):
        raise LookError(f"'{field}' must be a number from {low} to {high}")
    return min(max(value, low), high)


def _half_up(value: float) -> int:
    """The nearest whole number, a half going up: what JavaScript does with the same sum, so
    both sides store the same number (``round`` would send 2.5 to 2)."""
    return math.floor(value + 0.5)


def _dial(field: str, bounds: tuple[int, int]) -> Callable[[object], int | None]:
    def read(value: object) -> int | None:
        return None if value is None else _half_up(_number(field, value, bounds))

    return read


def _text_scale(value: object) -> float:
    return _half_up(_number("textScale", value, TEXT_SCALE) * 100) / 100


def _choice[E: StrEnum](field: str, kind: type[E]) -> Callable[[object], E]:
    def read(value: object) -> E:
        if isinstance(value, str) and value in kind:
            return kind(value)
        raise LookError(f"'{field}' must be one of: {', '.join(kind)}")

    return read


def _switch(field: str) -> Callable[[object], bool]:
    def read(value: object) -> bool:
        if isinstance(value, bool):
            return value
        raise LookError(f"'{field}' must be true or false")

    return read


def _collections_rows(value: object) -> tuple[CollectionsRow, ...]:
    names = value if isinstance(value, list) else []
    rows = tuple(CollectionsRow(v) for v in names if isinstance(v, str) and v in CollectionsRow)
    if not rows or len(rows) != len(names) or len(set(rows)) != len(rows):
        raise LookError(
            "'collectionsRows' must list at least one of "
            f"{', '.join(CollectionsRow)}, each once, in the order to show them"
        )
    return rows


# Sheet field → (attribute of Look, how to read its value). The whole list of fields.
_FIELDS: dict[str, tuple[str, Callable[[object], object]]] = {
    "theme": ("theme", _choice("theme", Theme)),
    "mode": ("mode", _choice("mode", Mode)),
    "accentHue": ("accent_hue", _dial("accentHue", ACCENT_HUE)),
    "corners": ("corners", _dial("corners", CORNERS)),
    "photoGap": ("photo_gap", _dial("photoGap", PHOTO_GAP)),
    "textScale": ("text_scale", _text_scale),
    "thumbSize": ("thumb_size", _choice("thumbSize", ThumbSize)),
    "showToday": ("show_today", _switch("showToday")),
    "startPage": ("start_page", _choice("startPage", StartPage)),
    "collectionsRows": ("collections_rows", _collections_rows),
    "dockLabels": ("dock_labels", _switch("dockLabels")),
}


def parse_look(raw: object) -> Look:
    """The look a sent sheet describes; fields it leaves out take their default.
    Raises LookError."""
    if not isinstance(raw, dict):
        raise LookError("a look is an object of named values")
    unknown = sorted(str(name) for name in raw if name not in _FIELDS)
    if unknown:
        raise LookError(
            f"unknown look field {', '.join(repr(n) for n in unknown)}; "
            f"a look has only: {', '.join(_FIELDS)}"
        )
    return _look({_FIELDS[name][0]: _FIELDS[name][1](value) for name, value in raw.items()})


def _look(values: dict[str, object]) -> Look:
    look = Look(**values)  # type: ignore[arg-type]  # each reader returns its field's type
    # no Today tab to start on
    return look if look.show_today else replace(look, start_page=StartPage.LIBRARY)


def read_look(stored: str | None) -> Look:
    """The look a stored sheet describes: each field that still passes, the default for each
    that does not, and the defaults for no sheet or for something that is not one."""
    try:
        raw = json.loads(stored or "null")
    except ValueError:
        return DEFAULT_LOOK
    if not isinstance(raw, dict):
        return DEFAULT_LOOK
    values: dict[str, object] = {}
    for name, (attribute, read) in _FIELDS.items():
        if name in raw:
            with contextlib.suppress(LookError):
                values[attribute] = read(raw[name])
    return _look(values)


def look_sheet(look: Look) -> dict[str, object]:
    """The look as the sheet the API sends and the store keeps."""
    sheet = {name: getattr(look, attribute) for name, (attribute, _) in _FIELDS.items()}
    sheet["collectionsRows"] = list(look.collections_rows)
    return sheet


def dump_look(look: Look) -> str:
    return json.dumps(look_sheet(look))
