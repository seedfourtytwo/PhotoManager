"""Build a print-ready album PDF (and PNG previews) from a folder of *synthetic* images.

    uv run python scripts/make_mock_library.py /tmp/mock-print --count 40 --size 1600
    uv run python scripts/demo_print.py /tmp/mock-print --out /tmp/print-demo \
        --trim a4-landscape --theme quiet --preview 1 2 3

Images are auto-rotated into print renditions first (what the library's print derivative does
for real), then laid out automatically. Never point this at real photos you intend to share.
"""

import argparse
import time
from pathlib import Path

import pyvips  # type: ignore[import-untyped]

from photo_assistant.adapters.typst_print import TypstPrintRenderer
from photo_assistant.app.print_album import PrintOptions, PrintPhoto, plan_print
from photo_assistant.domain.print_layout import TEXT_LAYOUT_ID, Page, auto_layout, trim_size
from photo_assistant.domain.print_theme import page_geometry, theme

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
INTRO = (
    "Every summer we said we would sort the photos. These are the ones that survived the "
    "phones, the old hard drive and the partner's camera roll, put in order at last.\n\n"
    "The pictures here are drawn by a script; the real ones stay at home."
)


def rendition(source: Path, folder: Path, index: int) -> PrintPhoto:
    image = pyvips.Image.new_from_file(str(source)).autorot()
    if image.interpretation not in ("srgb", "b-w"):
        image = image.colourspace("srgb")
    target = folder / f"{index:04d}.jpg"
    image.jpegsave(str(target), Q=92, strip=True)
    caption = f"{source.parent.name} · {source.stem}" if index % 3 == 0 else ""
    return PrintPhoto(target, image.width, image.height, caption=caption)


def collect(folder: Path, out: Path, limit: int) -> list[PrintPhoto]:
    sources = sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    renditions = out / "renditions"
    renditions.mkdir(parents=True, exist_ok=True)
    return [rendition(p, renditions, i) for i, p in enumerate(sources[:limit])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--out", type=Path, default=Path("/tmp/print-demo"))
    parser.add_argument("--trim", default="a4-landscape")
    parser.add_argument("--theme", default="quiet")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--crop-marks", action="store_true")
    parser.add_argument("--preview", type=int, nargs="*", default=[1, 2, 3])
    parser.add_argument("--ppi", type=float, default=96)
    args = parser.parse_args()

    photos = collect(args.folder, args.out, args.limit)
    geometry = page_geometry(theme(args.theme), trim_size(args.trim))
    pages = (
        Page(TEXT_LAYOUT_ID, (), text=INTRO),
        *auto_layout([p.aspect for p in photos], geometry),
    )
    options = PrintOptions(
        title="Summers, collected",
        subtitle=f"{len(photos)} photographs",
        trim=args.trim,
        theme=args.theme,
        cover_photo=photos[0] if photos else None,
        crop_marks=args.crop_marks,
        pages=pages,
        allow_low_resolution=True,
    )
    plan = plan_print(photos, options)
    renderer = TypstPrintRenderer()
    started = time.perf_counter()
    pdf = renderer.render_pdf(plan.job)
    elapsed = time.perf_counter() - started
    target = args.out / f"album-{args.trim}-{args.theme}.pdf"
    target.write_bytes(pdf)
    print(f"{target}: {plan.job.page_count} pages, {len(pdf) / 1e6:.1f} MB in {elapsed:.1f} s")
    print("layouts:", " ".join(p.layout_id for p in plan.job.pages))
    for issue in plan.issues:
        print(f"  {issue.level}: photo {issue.photo} prints at {issue.ppi:.0f} ppi")
    for number in args.preview:
        png = args.out / f"page-{args.trim}-{args.theme}-{number}.png"
        png.write_bytes(renderer.render_preview(plan.job, number, ppi=args.ppi))
        print(png)


if __name__ == "__main__":
    main()
