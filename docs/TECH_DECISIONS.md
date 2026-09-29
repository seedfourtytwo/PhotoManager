# Tech decisions

Each decision: what we chose, why, what we rejected, and when to revisit.
Researched September 2026; versions pinned at M1 kickoff.

## Build vs adopt

**Decision:** our own app. We *borrow ideas* from Immich and PhotoPrism (both open source,
both mature) but do not build on them.
**Why:** our differentiator is albums, print and the AI album planner, plus a quiet
Tufte-style UI. Immich is a large Postgres + Redis + multi-container stack optimised for
backup-from-phone; bending it into a print/album tool would mean fighting it.
**Borrowed ideas:** Immich's pipeline (thumbnail → CLIP embedding → face detect → cluster),
its exported ONNX CLIP models on Hugging Face, PhotoPrism's vision-model benchmarks for Ollama.
**Revisit if:** phone auto-backup becomes a must-have — then run Immich for backup only and
import from its library folder.

## Backend: Python 3.12 + FastAPI + uv

**Why:** the whole ML/imaging ecosystem is Python-first (ONNX Runtime, pyvips, typst-py);
FastAPI gives typed request/response models and an OpenAPI spec for a generated TS client;
it also matches C's Python learning goal. `uv` for fast, locked, reproducible envs.
**Rejected:** Node/TS backend (weaker ML story), Go/Rust (slower iteration for a 2-person app).

## Database: SQLite (WAL) + sqlite-vec

**Why:** one file, zero ops, trivially backed up, plenty for 10k–100k photos.
sqlite-vec adds vector KNN inside the same DB for CLIP and face embeddings.
**Risk:** sqlite-vec is pre-v1 and warns of breaking changes; pin the version and keep all
vector access behind the `Repository` port. At 10k × 512-d, brute-force KNN is milliseconds,
so we don't depend on its newer ANN indexes.
**Migrations:** numbered SQL files + `PRAGMA user_version`, with an automatic snapshot of the
database before any migration (FEATURES 11.6). Chosen over Alembic (built 2026-09-29): no ORM
in this codebase, and plain SQL keeps the schema readable.
**Rejected:** Postgres + pgvector (Immich's choice — more ops than we need now).
**Revisit if:** > 200k assets or many concurrent writers.

## Imaging: libvips (pyvips) + ExifTool + pillow-heif

- **libvips** for thumbnails/previews: fast, low-memory streaming, handles HEIC with libheif.
- **ExifTool** (via `pyexiftool`, one persistent process) — the reference for EXIF/XMP/
  QuickTime/maker notes, timezone fields, Live Photo pairing IDs.
- **BLAKE3** for content hashes (fast, streaming); **imagehash** pHash for near-duplicates.
- Derivatives as WebP: thumbnail fits 640 px (sharp on retina rows), preview fits 2048 px.
- The thumbnail is rendered **during import, from the source file, before copying**: it proves
  the file really decodes (a truncated JPEG still looks like a JPEG to ExifTool) and the photo
  appears in the library immediately. Previews follow in the background.
- **HEIC needs the HEVC decoder plugin** (`libheif-plugin-libde265` on Ubuntu). Without it libvips
  only reads the small embedded preview; found by the real-data run, now checked by `just setup`
  and installed in CI.
- Python libraries: `pyvips`, `pyexiftool` (one long-running ExifTool process), `blake3`.
- Rescans skip files whose size and modification time are unchanged (stored per source file,
  migration 0002); changed files are re-hashed, so an edit is never missed.

## Local ML: ONNX Runtime (CUDA on the RTX 2070, CPU fallback)

| Task | Model | Notes |
|---|---|---|
| Semantic search / auto-tags | CLIP-family ONNX export (e.g. Immich's ViT-B-32 or a multilingual M-CLIP variant for French + English queries) | Choose by benchmark on our own photos in M3 |
| Face detect + embed | **InsightFace `buffalo_l`** (chosen 2026-09-29 for accuracy) | Weights are **non-commercial research only**: fine for a private family library, never for anything we distribute. Downloaded on first run, never committed or bundled. YuNet + SFace (Apache-2.0) stays as a switchable fallback behind the same port. |
| Clustering | DBSCAN-style incremental clustering (as Immich does) | Pure-Python domain logic, unit tested |
| Geocoding | `reverse_geocoder` / GeoNames offline dump | No network |

## AI socket: Ollama adapter (optional)

**Why:** C already plans Ollama on a separate server, reached over Tailscale. Ollama's
`/api/chat` accepts base64 images and supports JSON-schema structured output.
**Candidate models (to benchmark in M5, not decided):** Gemma 4 (E4B / 12B) and Qwen-VL
family for captions; a mid-size text model for album planning. PhotoPrism's Aug 2026
benchmarks show large quality spreads between models on labelling, so we test on our photos.
**Constraint:** the RTX 2070 has 8 GB VRAM — only small vision models fit on the laptop;
the bigger ones wait for the server GPU (planned RTX 3060 12 GB).
**Design:** provider-agnostic port; an OpenAI-compatible adapter can be added later (LM Studio,
llama.cpp server) with no domain change.

## Sources

| Source | Tool | Status / caveats |
|---|---|---|
| Local folder / external disk | direct | Primary path, M1 |
| MEGA | `rclone` mega backend | Works; rclone docs warn MEGA may block logins under heavy use → throttle (`--tpslimit`), pull once into staging |
| Proton Drive | `rclone` protondrive backend | **Beta, reverse-engineered API.** Known 2FA/re-auth pain. **Reads only "My files", not the Photos section** that Proton's iPhone auto-backup writes to (rclone issue #7832, open). So Proton works as a source for photos put in a normal folder, not for Proton's automatic phone backup — revisit when rclone or Proton's official SDK exposes Photos. Free plan is 5 GB max. |
| iPhone | `libimobiledevice` + `ifuse` (USB/Wi-Fi) or iCloud "Download originals" folder | Wireless ADB does not apply to iPhone |
| Android | `adb pull /sdcard/DCIM` over wireless debugging | Could-have |

All sources are **pull-only** into `staging/`; the import step is the same for all.

## Frontend: SvelteKit + TypeScript, static build, PWA

**Why:** small bundles and fast rendering on phones; one responsive codebase for laptop and
mobile; installable as a PWA (no app-store work). Built as static files served by FastAPI.
- Virtualised justified grid (own component, tested) — the core performance piece.
- Charts (calendar heat map, small multiples): D3 scales + hand-written SVG, no chart kit
  with default chrome (see DESIGN_PRINCIPLES).
- Map: MapLibre GL with a muted, self-hostable style (e.g. Protomaps PMTiles file) — no tile API keys.
- API client generated from OpenAPI (`openapi-typescript`) — one source of truth for types.
**Rejected:** React (heavier, no clear gain here), native mobile apps (later, if ever).

## Print: Typst (via `typst` Python package)

**Why:** a real typesetting engine: precise page geometry, bleed, embedded fonts, images at
full resolution, PDF output, fast compile, templates as code we can test. `typst-py` compiles
in-process and accepts `sys_inputs` → our album JSON goes straight in.
Pin a reproducible `timestamp` so the same album produces a byte-identical PDF → golden tests.
**Rejected:** HTML→PDF via headless Chrome (weak bleed/colour control), ReportLab (verbose),
LaTeX (heavy toolchain).
**Open:** CMYK/PDF-X for professional print labs — Typst targets PDF/A and PDF/UA today; most
consumer photo-book services accept sRGB PDFs. Confirm with the lab we pick (OPEN_QUESTIONS).
**Fonts:** only the families compiled into Typst (Libertinus Serif, New Computer Modern,
DejaVu Sans Mono), system fonts ignored: no downloads, identical output on laptop and server.
Wiring: `docs/wiring/print.md`.

## Download, convert and edit

- **Conversion/resize:** libvips (already in the stack) writes JPEG, PNG, WebP; HEIC decoded via
  libheif. No extra dependency for the converter.
- **ZIP:** streamed with `zipstream-ng` (stored, not re-compressed — photos don't compress),
  so large exports need no temp space on the server.
- **Phone save:** Web Share API with files (supported by iOS Safari) → "Save to Photos".
- **Editor:** recipes are data; preview in the browser with CSS transforms/canvas, final render
  with libvips. Colour adjustments deferred until preview/export parity is covered by
  golden-image tests (M5).

## Backup: restic (+ rclone for remote targets)

**Why:** incremental, content-deduplicated, encrypted, versioned snapshots with retention
policies and built-in `check`/`restore` — exactly the feature list, battle-tested, single binary.
Its rclone backend reaches every target type we care about.
**Rejected:** plain `rclone sync` (a mirror, not a backup — a deletion or corruption is
faithfully copied), BorgBackup (needs borg on the target side; no native cloud backends).

## Phones: web now, free Shortcuts upload, native app parked

**No paid tools** (decided 2026-09-29). The web app does browsing, editing, downloads and
hand-picked uploads on any phone or laptop. Automatic iPhone upload uses **Apple Shortcuts**
(built into iOS, free): a personal automation posts new photos to our upload API with a
per-device token. The server can't pull from a phone and a web page can't run in the background
on iOS, so this is the only free automatic route without our own app.
**Rejected for now:** PhotoSync Premium (paid); own iOS app (needs the $99/yr Apple Developer
Program, or re-signing every 7 days with a free Apple ID). If built later: Capacitor around the
same SvelteKit UI, so it has every web feature.

## Tooling

| Concern | Tool |
|---|---|
| Task runner | `just` |
| Python lint/format/types | ruff, ruff format, mypy --strict (domain/app), pyright in editor OK |
| Python tests | pytest, hypothesis, pytest-cov, syrupy (snapshots), import-linter |
| Web lint/format/types | eslint, prettier, svelte-check, TypeScript strict |
| Web tests | Vitest + Testing Library, Playwright (E2E, mobile + desktop viewports), axe-core |
| Pre-commit | pre-commit (ruff, prettier, gitleaks, no large files) |
| CI | GitHub Actions: lint → types → unit → integration (with exiftool/libvips in container) → E2E |
| Versioning | Conventional Commits, release-please |
