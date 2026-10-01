"""Album themes (FEATURES §5.3): a small curated set, as data."""

import re

import pytest

from photo_assistant.domain.print_layout import SAFE_MARGIN_MM, trim_size
from photo_assistant.domain.print_theme import (
    BUNDLED_FONTS,
    THEMES,
    UnknownThemeError,
    page_geometry,
    theme,
)

HEX = re.compile(r"^#[0-9A-F]{6}$")


def test_curated_themes() -> None:
    assert list(THEMES) == ["quiet", "warm", "night"]
    assert theme("night").paper != theme("quiet").paper


def test_unknown_theme_is_a_typed_error() -> None:
    with pytest.raises(UnknownThemeError, match="neon"):
        theme("neon")


@pytest.mark.parametrize("theme_id", list(THEMES))
def test_themes_use_only_fonts_bundled_with_typst(theme_id: str) -> None:
    t = theme(theme_id)
    assert t.font in BUNDLED_FONTS
    assert all(HEX.match(c) for c in (t.paper, t.ink, t.ink_secondary))
    assert t.caption_size_pt < t.text_size_pt < t.title_size_pt


def test_margins_scale_with_the_page_but_respect_the_safe_margin() -> None:
    quiet = theme("quiet")
    a4 = page_geometry(quiet, trim_size("a4-portrait"))
    a5 = page_geometry(quiet, trim_size("a5-portrait"))
    assert a4.margin_mm > a5.margin_mm >= SAFE_MARGIN_MM
    assert a4.margin_mm == pytest.approx(quiet.margin_fraction * 210)
    assert a4.gutter_mm == quiet.gutter_mm
    assert a4.caption_band_mm == quiet.caption_band_mm
