"""Album themes (FEATURES §5.3): paper, ink, one serif family, proportions. Data, not code.

Fonts are limited to the ones compiled into the Typst engine, so printing never downloads
anything and the same album renders identically on the laptop and on the home server.
"""

from dataclasses import dataclass

from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.print_layout import PageGeometry, TrimSize

BUNDLED_FONTS = frozenset({"Libertinus Serif", "New Computer Modern", "DejaVu Sans Mono"})


class UnknownThemeError(InvalidError):
    """A theme id that is not one of the curated themes."""


@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    paper: str  # page colour, sRGB hex
    ink: str  # titles and body text
    ink_secondary: str  # captions: lighter by value, not a different hue
    font: str
    title_size_pt: float
    text_size_pt: float
    caption_size_pt: float
    margin_fraction: float  # of the page's short side
    gutter_mm: float
    caption_band_mm: float


THEMES: dict[str, Theme] = {
    t.id: t
    for t in (
        Theme(
            "quiet",
            "Quiet — white paper, Libertinus",
            paper="#FFFFFF",
            ink="#1A1A1A",
            ink_secondary="#6B6B6B",
            font="Libertinus Serif",
            title_size_pt=30,
            text_size_pt=11,
            caption_size_pt=8.5,
            margin_fraction=0.085,
            gutter_mm=3.5,
            caption_band_mm=9.0,
        ),
        Theme(
            "warm",
            "Warm — cream paper, Computer Modern",
            paper="#F5EFE3",
            ink="#2B2620",
            ink_secondary="#7A6F61",
            font="New Computer Modern",
            title_size_pt=28,
            text_size_pt=10.5,
            caption_size_pt=8,
            margin_fraction=0.095,
            gutter_mm=4.0,
            caption_band_mm=9.0,
        ),
        Theme(
            "night",
            "Night — dark pages, Libertinus",
            paper="#161616",
            ink="#E8E6E1",
            ink_secondary="#9A968F",
            font="Libertinus Serif",
            title_size_pt=30,
            text_size_pt=11,
            caption_size_pt=8.5,
            margin_fraction=0.07,
            gutter_mm=3.0,
            caption_band_mm=9.0,
        ),
    )
}


def theme(theme_id: str) -> Theme:
    try:
        return THEMES[theme_id]
    except KeyError:
        raise UnknownThemeError(f"unknown theme: {theme_id!r}") from None


def page_geometry(t: Theme, trim: TrimSize) -> PageGeometry:
    short_side = min(trim.width_mm, trim.height_mm)
    return PageGeometry(
        trim,
        margin_mm=t.margin_fraction * short_side,
        gutter_mm=t.gutter_mm,
        caption_band_mm=t.caption_band_mm,
    )
