"""Integration: the Typst renderer turns print jobs into real PDFs and PNG previews.

Images are drawn here with libvips (gradients and discs), never real photos.
"""

import hashlib
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pyvips  # type: ignore[import-untyped]
import typst

from photo_assistant.adapters.typst_print import TypstPrintRenderer
from photo_assistant.app.print_album import PrintOptions, PrintPhoto, plan_print
from photo_assistant.domain.print_layout import BLEED_MM, MM_PER_INCH, Page
from photo_assistant.domain.print_theme import BUNDLED_FONTS, THEMES
from photo_assistant.ports.printing import PrintJob, PrintRenderer, PrintRenderError

pytestmark = pytest.mark.integration

GOLDENS = Path(__file__).parent.parent / "fixtures" / "print"
PT_PER_MM = 72 / MM_PER_INCH


def draw(path: Path, width: int, height: int, tint: tuple[int, int, int]) -> PrintPhoto:
    """A gradient with a disc in the middle: crops and orientation are easy to see."""
    xy = pyvips.Image.xyz(width, height)
    fx, fy = xy[0] / width, xy[1] / height
    bands = [fx * c + fy * (255 - c) * 0.5 for c in tint]
    image = bands[0].bandjoin(bands[1:])
    disc = ((xy[0] - width / 2) ** 2 + (xy[1] - height / 2) ** 2) < (min(width, height) / 4) ** 2
    image = disc.ifthenelse([245, 240, 230], image).cast("uchar").copy(interpretation="srgb")
    if path.suffix == ".png":
        image.pngsave(str(path))
    else:
        image.jpegsave(str(path), Q=85, strip=True)
    return PrintPhoto(path, width, height)


@pytest.fixture(scope="module")
def photos(tmp_path_factory: pytest.TempPathFactory) -> list[PrintPhoto]:
    folder = tmp_path_factory.mktemp("print-images")
    sizes = [(1600, 1200), (1200, 1600), (1600, 1067), (1200, 1600), (1600, 1600), (1600, 900)]
    tints = [(200, 90, 40), (40, 120, 200), (90, 160, 80), (180, 60, 140), (220, 180, 40)]
    return [
        draw(folder / f"img-{i}.jpg", w, h, tints[i % len(tints)]) for i, (w, h) in enumerate(sizes)
    ]


@pytest.fixture(scope="module")
def renderer() -> TypstPrintRenderer:
    return TypstPrintRenderer(timestamp=datetime(2026, 1, 1, tzinfo=UTC))


def job_for(photos: Sequence[PrintPhoto], **options: object) -> PrintJob:
    values: dict[str, object] = {"title": "Summer in the Dordogne", "subtitle": "July 2026"}
    values.update(options)
    return plan_print(photos, PrintOptions(**values)).job  # type: ignore[arg-type]


def media_boxes(pdf: bytes) -> list[tuple[float, float]]:
    """(width, height) in points of every page — a tiny parser; Typst writes no object streams."""
    boxes = re.findall(rb"/MediaBox\s*\[\s*([\d.\s-]+)\]", pdf)
    sizes = []
    for box in boxes:
        x0, y0, x1, y1 = (float(v) for v in box.split())
        sizes.append((x1 - x0, y1 - y0))
    return sizes


def test_satisfies_the_port(renderer: TypstPrintRenderer) -> None:
    port: PrintRenderer = renderer
    assert port is renderer


def test_every_theme_font_is_bundled_with_typst() -> None:
    families = set(typst.Fonts(include_system_fonts=False).families())
    assert families >= BUNDLED_FONTS
    assert {t.font for t in THEMES.values()} <= families


def test_one_pdf_page_per_album_page_sized_trim_plus_bleed(
    renderer: TypstPrintRenderer, photos: list[PrintPhoto]
) -> None:
    job = job_for(photos, trim="a4-portrait")
    pdf = renderer.render_pdf(job)
    assert pdf.startswith(b"%PDF-")
    boxes = media_boxes(pdf)
    assert len(boxes) == job.page_count
    width, height = (210 + 2 * BLEED_MM) * PT_PER_MM, (297 + 2 * BLEED_MM) * PT_PER_MM
    for w, h in boxes:
        assert (w, h) == (pytest.approx(width, abs=0.01), pytest.approx(height, abs=0.01))


def test_images_are_embedded_at_full_resolution_and_fonts_embedded(
    renderer: TypstPrintRenderer, photos: list[PrintPhoto]
) -> None:
    pdf = renderer.render_pdf(job_for(photos))
    assert len(re.findall(rb"/Subtype\s*/Image", pdf)) == len(photos)
    assert pdf.count(b"/Width 1600") + pdf.count(b"/Width 1200") == len(photos)
    assert b"/DCTDecode" in pdf  # JPEGs pass through without re-compression
    assert re.search(rb"/FontFile[23]?", pdf)
    assert b"Summer in the Dordogne" in pdf


def test_same_album_gives_byte_identical_pdf(
    renderer: TypstPrintRenderer, photos: list[PrintPhoto]
) -> None:
    job = job_for(photos, theme="warm", trim="square-20")
    first, second = renderer.render_pdf(job), renderer.render_pdf(job)
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert b"2026" in first  # the pinned creation date, not "now"


def test_crop_marks_add_a_slug_outside_the_bleed(
    renderer: TypstPrintRenderer, photos: list[PrintPhoto]
) -> None:
    job = job_for(photos[:1], crop_marks=True, trim="a5-landscape")
    (w, h), *_ = media_boxes(renderer.render_pdf(job))
    slug = TypstPrintRenderer.SLUG_MM
    assert w == pytest.approx((210 + 2 * (BLEED_MM + slug)) * PT_PER_MM, abs=0.01)
    assert h == pytest.approx((148 + 2 * (BLEED_MM + slug)) * PT_PER_MM, abs=0.01)


def test_text_pages_captions_and_every_layout_render(
    renderer: TypstPrintRenderer, photos: list[PrintPhoto]
) -> None:
    captioned = [
        PrintPhoto(p.image_path, p.pixel_w, p.pixel_h, caption=f"Photo {i}")
        for i, p in enumerate(photos)
    ]
    pages = (
        Page("text", (), text="A week of long evenings.\n\nWritten for the family."),
        Page("full-bleed", (0,)),
        Page("hero-two", (0, 1, 2)),
        Page("hero-two-side", (0, 1, 2)),
        Page("three-grid", (1, 3, 1)),
        Page("four-grid", (0, 2, 4, 5)),
        Page("two-stacked", (0, 2)),
        Page("two-side", (1, 3)),
    )
    job = job_for(captioned, pages=pages, theme="night", allow_low_resolution=True)
    pdf = renderer.render_pdf(job)
    assert len(media_boxes(pdf)) == len(pages) + 1


def test_preview_is_one_png_page_at_the_requested_ppi(
    renderer: TypstPrintRenderer, photos: list[PrintPhoto]
) -> None:
    job = job_for(photos)
    png = renderer.render_preview(job, 2, ppi=40)
    image = pyvips.Image.new_from_buffer(png, "")
    expected_width = (297 + 2 * BLEED_MM) / MM_PER_INCH * 40
    assert image.width == pytest.approx(expected_width, abs=1)
    cover = pyvips.Image.new_from_buffer(renderer.render_preview(job, 1, ppi=40), "")
    assert cover.width == image.width


def test_preview_page_out_of_range(renderer: TypstPrintRenderer, photos: list[PrintPhoto]) -> None:
    job = job_for(photos[:1], cover=False)
    with pytest.raises(PrintRenderError, match="page 2"):
        renderer.render_preview(job, 2)


def test_unreadable_image_is_a_render_error(renderer: TypstPrintRenderer, tmp_path: Path) -> None:
    missing = PrintPhoto(tmp_path / "gone.jpg", 1600, 1200)
    with pytest.raises(PrintRenderError, match=r"gone\.jpg"):
        renderer.render_pdf(job_for([missing]))


@pytest.mark.parametrize(
    ("name", "theme", "trim", "pages"),
    [
        ("quiet-hero", "quiet", "a4-landscape", (Page("hero-two-side", (0, 1, 2)),)),
        ("warm-two", "warm", "a5-portrait", (Page("two-stacked", (2, 0)),)),
    ],
)
def test_page_matches_its_golden_render(
    renderer: TypstPrintRenderer,
    tmp_path: Path,
    name: str,
    theme: str,
    trim: str,
    pages: tuple[Page, ...],
) -> None:
    # PNG inputs keep the golden independent of the JPEG encoder on the machine.
    shapes = [(900, 600, (200, 90, 40)), (600, 800, (40, 120, 200)), (800, 600, (90, 160, 80))]
    images = [
        PrintPhoto(draw(tmp_path / f"g{i}.png", w, h, c).image_path, w, h, caption=f"No. {i}")
        for i, (w, h, c) in enumerate(shapes)
    ]
    job = job_for(images, theme=theme, trim=trim, pages=pages, allow_low_resolution=True)
    png = renderer.render_preview(job, 2, ppi=36)
    golden = GOLDENS / f"golden-{name}.png"
    if os.environ.get("PA_UPDATE_GOLDENS") == "1":
        golden.write_bytes(png)
    actual = pyvips.Image.new_from_buffer(png, "")
    expected = pyvips.Image.new_from_file(str(golden))
    assert (actual.width, actual.height) == (expected.width, expected.height)
    assert (actual - expected).abs().avg() < 1.0
