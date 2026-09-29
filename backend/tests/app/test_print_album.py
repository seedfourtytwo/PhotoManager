"""Album → print job → PDF, orchestrated with a fake renderer (FEATURES §6.1, §6.2)."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from photo_assistant.app.print_album import (
    EmptyAlbumError,
    InvalidPagesError,
    PrintBlockedError,
    PrintOptions,
    PrintPhoto,
    plan_print,
    preview_page,
    print_album,
)
from photo_assistant.domain.print_layout import (
    FULL,
    Page,
    Resolution,
    UnknownLayoutError,
    UnknownTrimSizeError,
)
from photo_assistant.domain.print_theme import UnknownThemeError
from photo_assistant.ports.printing import PrintJob, PrintRenderer


@dataclass
class FakeRenderer:
    pdfs: list[PrintJob] = field(default_factory=list)
    previews: list[tuple[PrintJob, int, float]] = field(default_factory=list)

    def render_pdf(self, job: PrintJob) -> bytes:
        self.pdfs.append(job)
        return b"%PDF-fake"

    def render_preview(self, job: PrintJob, page_number: int, ppi: float = 96) -> bytes:
        self.previews.append((job, page_number, ppi))
        return b"PNG-fake"


def photo(n: int, w: int = 4000, h: int = 3000, caption: str = "") -> PrintPhoto:
    return PrintPhoto(Path(f"/lib/print/{n}.jpg"), w, h, caption=caption)


def slot_paths(job: PrintJob) -> list[Path]:
    return [s.image_path for p in job.pages for s in p.slots]


def test_fake_renderer_satisfies_the_port() -> None:
    renderer: PrintRenderer = FakeRenderer()
    assert renderer is not None


def test_every_photo_is_printed_once_in_album_order() -> None:
    photos = [photo(i, *((3000, 4000) if i % 3 else (4000, 3000))) for i in range(11)]
    job = plan_print(photos, PrintOptions(title="Summer")).job
    assert slot_paths(job) == [p.image_path for p in photos]
    assert job.title == "Summer"
    assert (job.trim.id, job.theme.id) == ("a4-landscape", "quiet")


def test_cover_page_holds_title_and_optional_photo() -> None:
    cover = photo(99)
    job = plan_print([photo(1)], PrintOptions(title="T", cover_photo=cover)).job
    assert job.cover is not None and job.cover.photo is not None
    assert job.cover.photo.image_path == cover.image_path
    assert job.cover.photo.crop == FULL
    assert job.page_count == 2
    no_cover = plan_print([photo(1)], PrintOptions(title="T", cover=False)).job
    assert no_cover.cover is None and no_cover.page_count == 1


def test_frames_and_crops_agree() -> None:
    job = plan_print([photo(i) for i in range(8)], PrintOptions(title="T")).job
    for page in job.pages:
        for slot in page.slots:
            cropped_aspect = (slot.crop.w * slot.pixel_w) / (slot.crop.h * slot.pixel_h)
            assert cropped_aspect == pytest.approx(slot.frame.aspect, rel=1e-6)


def test_focal_point_steers_the_crop() -> None:
    pages = (Page("four-grid", (0, 1, 2, 3)),)
    wide = [
        PrintPhoto(Path(f"/p/{i}.jpg"), 6000, 2000, focal=(0.0, 0.5)) for i in range(4)
    ]
    job = plan_print(wide, PrintOptions(title="T", pages=pages, allow_low_resolution=True)).job
    assert all(s.crop.x == 0 for s in job.pages[0].slots)


def test_captions_of_a_page_are_joined() -> None:
    photos = [photo(1, 3000, 4000, "Anna"), photo(2, 3000, 4000), photo(3, 3000, 4000, "Ben")]
    pages = (Page("three-grid", (0, 1, 2)),)
    job = plan_print(photos, PrintOptions(title="T", pages=pages)).job
    assert job.pages[0].caption == "Anna · Ben"


def test_manual_pages_override_the_auto_layout_and_allow_text_pages() -> None:
    pages = (Page("text", (), text="The summer we…"), Page("single", (1,)), Page("single", (0,)))
    job = plan_print([photo(1), photo(2)], PrintOptions(title="T", pages=pages)).job
    assert [p.layout_id for p in job.pages] == ["text", "single", "single"]
    assert job.pages[0].text == "The summer we…"
    assert slot_paths(job) == [photo(2).image_path, photo(1).image_path]


@pytest.mark.parametrize(
    "pages",
    [
        (Page("four-grid", (0, 1)),),  # wrong number of photos for the layout
        (Page("single", (5,)),),  # no such photo
        (Page("text", (0,)),),  # text pages hold no photos
    ],
)
def test_invalid_manual_pages_are_rejected(pages: tuple[Page, ...]) -> None:
    with pytest.raises(InvalidPagesError):
        plan_print([photo(1)], PrintOptions(title="T", pages=pages))


def test_unknown_layout_trim_or_theme_are_typed_errors() -> None:
    with pytest.raises(UnknownLayoutError):
        plan_print([photo(1)], PrintOptions(title="T", pages=(Page("zigzag", (0,)),)))
    with pytest.raises(UnknownTrimSizeError):
        plan_print([photo(1)], PrintOptions(title="T", trim="b5"))
    with pytest.raises(UnknownThemeError):
        plan_print([photo(1)], PrintOptions(title="T", theme="neon"))


def test_nothing_to_print() -> None:
    with pytest.raises(EmptyAlbumError):
        plan_print([], PrintOptions(title="T", cover=False))
    assert plan_print([], PrintOptions(title="Only a cover")).job.page_count == 1


def test_resolution_issues_name_the_photo_and_level() -> None:
    # A 1200 px wide photo alone on an A4 landscape page prints well below 150 ppi.
    photos = [photo(0), photo(1, 1200, 900)]
    pages = (Page("single", (0,)), Page("single", (1,)))
    plan = plan_print(photos, PrintOptions(title="T", pages=pages))
    (issue,) = plan.issues
    assert (issue.photo, issue.level) == (1, Resolution.BLOCK)
    assert issue.image_path == photos[1].image_path
    assert issue.ppi < 150
    assert plan.blocked


def test_soft_photos_warn_but_still_print() -> None:
    pages = (Page("single", (0,)),)
    renderer = FakeRenderer()
    result = print_album([photo(0, 1800, 1350)], PrintOptions(title="T", pages=pages), renderer)
    assert [i.level for i in result.issues] == [Resolution.WARN]
    assert result.pdf == b"%PDF-fake"
    assert result.page_count == 2


def test_blocking_photos_stop_the_export_unless_allowed() -> None:
    photos, renderer = [photo(0, 600, 450)], FakeRenderer()
    with pytest.raises(PrintBlockedError) as err:
        print_album(photos, PrintOptions(title="T"), renderer)
    assert err.value.issues[0].level is Resolution.BLOCK
    assert renderer.pdfs == []
    print_album(photos, PrintOptions(title="T", allow_low_resolution=True), renderer)
    assert len(renderer.pdfs) == 1


def test_cover_photo_resolution_is_checked_too() -> None:
    plan = plan_print([], PrintOptions(title="T", cover_photo=photo(7, 500, 400)))
    (issue,) = plan.issues
    assert issue.photo is None and issue.level is Resolution.BLOCK


def test_preview_renders_one_page_even_when_blocked() -> None:
    renderer = FakeRenderer()
    png = preview_page([photo(0, 600, 450)], PrintOptions(title="T"), renderer, 2, ppi=72)
    assert png == b"PNG-fake"
    ((_, number, ppi),) = renderer.previews
    assert (number, ppi) == (2, 72)
    with pytest.raises(InvalidPagesError):
        preview_page([photo(0)], PrintOptions(title="T"), renderer, 3)
