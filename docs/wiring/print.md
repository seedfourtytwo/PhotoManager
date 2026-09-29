# Wiring: album → print (FEATURES §5.3, §5.4, §6)

The print engine lives on `feat/print` and works on its own. No route, service or migration uses
it yet. This page says what the integrator has to add.

## What exists

| Layer | Module | Role |
|---|---|---|
| domain | `domain/print_layout.py` | trim presets, bleed 3 mm and safe margin 5 mm, layout templates (as data), `PageGeometry`, `auto_layout`, `place_page`, `cover_crop`, `effective_ppi`, `check_resolution` |
| domain | `domain/print_theme.py` | `THEMES` (`quiet`, `warm`, `night`), `page_geometry(theme, trim)` |
| port | `ports/printing.py` | `PrintRenderer` Protocol; `PrintJob`, `PrintPage`, `PrintSlot`, `PrintCover`; `PrintRenderError` |
| app | `app/print_album.py` | `plan_print`, `print_album`, `preview_page`; `PrintPhoto`, `PrintOptions`; `PrintBlockedError`, `InvalidPagesError`, `EmptyAlbumError` |
| adapter | `adapters/typst_print.py` + `typst_templates/album.typ` | `TypstPrintRenderer(timestamp=…)` |

Layout ids: `full-bleed`, `single`, `two-side`, `two-stacked`, `three-grid`, `hero-two`,
`hero-two-side`, `four-grid`, `text`. Trim ids: `a4-portrait`, `a4-landscape`, `a5-portrait`,
`a5-landscape`, `square-20`, `us-letter`.

## Proposed endpoints

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/api/print/options` | – | `{trims:[{id,label,width_mm,height_mm}], themes:[{id,label,paper,ink,font}], layouts:[{id,label,capacity}]}`, read straight from `TRIM_SIZES`, `THEMES` and `LAYOUTS` |
| POST | `/api/albums/{id}/print/plan` | `PrintRequest` | `{pages:[{layout_id, photos:[asset_id], text}], issues:[{asset_id, ppi, level}], page_count}`, for the page editor (no rendering) |
| POST | `/api/albums/{id}/print` | `PrintRequest` | `200 application/pdf` (`Content-Disposition: attachment; filename="<album title>.pdf"`), plus an `X-Print-Warnings: <n>` header; `422 {detail, issues}` when blocked |
| GET | `/api/albums/{id}/print/preview` | `?page=N&trim=&theme=&ppi=96` | `200 image/png` for one page (1-based; the cover is page 1) |

```
PrintRequest = {
  trim: "a4-landscape", theme: "quiet", cover: true, crop_marks: false,
  pages?: [{layout_id, asset_ids:[id], text?}],    # manual layout; omit for automatic
  allow_low_resolution?: false
}
```

Permissions: printing puts full-resolution pixels into a file, so it needs `download` on every
item, the same rule as the ZIP export. Items the user can't see are left out, as they are in the
album view.

## Mapping album items to `PrintPhoto`

In album order, for each item:

1. **A print rendition, not the original.** Typst reads JPEG, PNG, GIF, WebP and SVG. It
   cannot read HEIC or RAW, and it does not apply EXIF orientation reliably. The renderer
   therefore needs a *print derivative*:
   `derived/print/<hash[:2]>/<hash>-<recipe_hash>.jpg`. It is built with libvips from
   `LibraryStore.absolute(asset.library_path)`: autorotate, apply the edit recipe (rotate, flip,
   crop, straighten), convert to sRGB, keep the full resolution, save JPEG at Q 92 with ICC
   stripped. Cache it by `(content_hash, recipe_hash)`. Add a `"print"` kind to
   `DERIVATIVE_KINDS` or write a sibling helper; that choice is the integrator's.
   `scripts/demo_print.py::rendition` is a short reference.
2. `PrintPhoto(image_path=<absolute rendition path>, pixel_w, pixel_h, caption, focal)`. Take
   `pixel_w/h` from the **rendition** after the recipe is applied, because they drive the ppi
   check. `caption` is the album item caption (empty until §5.5 exists). `focal` defaults to the
   centre; a face or AI saliency point can go here later.
3. `cover_photo` = the album's `cover_asset_id` mapped the same way, or `None`.
4. Manual `pages` from the request: map `asset_ids` to indices into that list, then
   `Page(layout_id, indices, text)`. `InvalidPagesError` / `UnknownLayoutError` → 422.

Service sketch (in `api/services.py`, which only the integrator edits):

```python
renderer = TypstPrintRenderer(timestamp=album.updated_at)  # same album → same bytes
photos = [to_print_photo(item) for item in album.items]     # builds/caches renditions
options = PrintOptions(title=album.title, subtitle=album.description or "", trim=req.trim,
                       theme=req.theme, cover=req.cover, cover_photo=cover,
                       crop_marks=req.crop_marks, pages=pages,
                       allow_low_resolution=req.allow_low_resolution)
result = print_album(photos, options, renderer)             # PrintBlockedError → 422
```

**Previews:** `preview_page(...)` renders only the requested page. Point `image_path` at the
existing 2048 px `preview` derivative, but keep the rendition's `pixel_w/h`. A preview then
never waits for a full-resolution rendition. The PNG is at `ppi`
(96 gives about 1150 px across A4 landscape).

**Performance:** 40 synthetic 1600 px photos compile to a 16-page PDF in about 0.2 s.
Full-resolution 12 MP JPEGs are embedded as-is (DCT passthrough), so compile time stays low but
the PDF is roughly the sum of the JPEG sizes. Run large albums as a job (FEATURES 4b.8) and
stream the file.

**Reproducibility:** fonts are only the three compiled into Typst (Libertinus Serif, New Computer
Modern, DejaVu Sans Mono; system fonts are ignored), and the creation date is the `timestamp`
you pass. The same job and timestamp give byte-identical PDFs (this is tested).

## Tests to add when wiring

- API: `POST /print` returns `application/pdf` and a MediaBox of trim + 6 mm; blocked → 422 with
  issues; no `download` permission → 403; preview `page=0` → 422.
- E2E journey "album → PDF" (ENGINEERING_RULES §3).

## Known gaps

- sRGB PDF 1.7 only; no CMYK and no PDF/X (Typst supports PDF/A and PDF/UA, not PDF/X). No
  TrimBox or BleedBox. Most consumer photo-book labs accept this; confirm with the lab
  (OPEN_QUESTIONS).
- Crop marks enlarge the sheet by a 10 mm slug per side. Without them the sheet is exactly trim +
  2 × bleed.
- Full-bleed pages print no caption (it would sit on the photo). The page editor should warn
  about this or move the caption.
- Duplicate photos across pages are allowed in manual layouts, but not detected.
- Contact sheets and single prints (6.4) are not built. A `grid-N` layout plus `a4` covers it.
