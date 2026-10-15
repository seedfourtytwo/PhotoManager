# Tech decisions

Each decision: what we chose, why, what we rejected, and when to revisit.
Researched September 2026; versions pinned at M1 kickoff.

## Build vs adopt

**Decision:** our own app. We _borrow ideas_ from Immich and PhotoPrism (both open source,
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
FastAPI gives typed request/response models and an OpenAPI spec (the web client's types are
written by hand from `docs/contracts/api-v1.md`, not generated from it);
it also matches C's Python learning goal. `uv` for fast, locked, reproducible envs.
**Rejected:** Node/TS backend (weaker ML story), Go/Rust (slower iteration for a 2-person app).

## Database: SQLite (WAL) + sqlite-vec

**Why:** one file, zero ops, trivially backed up, plenty for 10k–100k photos.
sqlite-vec adds vector KNN inside the same DB for CLIP and face embeddings.
**Risk:** sqlite-vec is pre-v1 and warns of breaking changes; it is held to 0.1.x
(`sqlite-vec~=0.1.9`) and all vector access is behind the `MlStore` port (`ports/ml.py`,
`adapters/ml_store.py`). At 10k × 512-d, brute-force KNN is milliseconds,
so we don't depend on its newer ANN indexes.
**Migrations:** numbered SQL files + `PRAGMA user_version`, with an automatic snapshot of the
database before any migration (FEATURES 11.6). Chosen over Alembic (built 2026-09-29): no ORM
in this codebase, and plain SQL keeps the schema readable.
**Rejected:** Postgres + pgvector (Immich's choice — more ops than we need now).
**Revisit if:** > 200k assets or many concurrent writers.

## Imaging: libvips (pyvips) + ExifTool

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
  and `just doctor`, and in the CI file's package list.
- Python libraries: `pyvips`, `pyexiftool` (one long-running ExifTool process), `blake3`.
- Rescans skip files whose size and modification time are unchanged (stored per source file,
  migration 0002); changed files are re-hashed, so an edit is never missed.

## Accounts, places, groups, downloads (M2 dependencies)

- **argon2-cffi** — argon2id PIN hashes (RFC 9106 low-memory profile: t=3, 64 MiB).
- **reverse_geocoder** — used only for its bundled GeoNames cities file (population > 1000);
  we build our own k-d tree over unit-sphere points with **scipy** (declared; also its dependency) and drop
  places more than 50 km away. Fully offline. **pycountry** turns ISO codes into country
  names (offline data).
- **imagehash** + **Pillow** — 64-bit pHash of each thumbnail for near-duplicates
  (≤ 6 bits within 10 min) next to bursts (same camera within 3 s).
- **zipstream-ng** — ZIPs streamed while sent, entries stored (not deflated).
- ExifTool (already installed) strips location/metadata from _temporary copies_ for downloads.

## Local ML: ONNX Runtime (CUDA on the RTX 2070, CPU fallback)

| Task                        | Model                                                                                                          | Notes                                                                                                                                                                                                                                                   |
| --------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Semantic search / auto-tags | CLIP-family ONNX export (e.g. Immich's ViT-B-32 or a multilingual M-CLIP variant for French + English queries) | Choose by benchmark on our own photos in M3                                                                                                                                                                                                             |
| Face detect + embed         | **InsightFace `buffalo_l`** (chosen 2026-09-29 for accuracy)                                                   | Weights are **non-commercial research only**: fine for a private family library, never for anything we distribute. Downloaded on first run, never committed or bundled. YuNet + SFace (Apache-2.0) stays as a switchable fallback behind the same port. |
| Clustering                  | DBSCAN-style incremental clustering (as Immich does)                                                           | Pure-Python domain logic, unit tested                                                                                                                                                                                                                   |
| Geocoding                   | `reverse_geocoder` / GeoNames offline dump                                                                     | No network                                                                                                                                                                                                                                              |

Python dependencies for local ML (added 2026-09-30, branch `feat/ml`): `onnxruntime` (runs
CLIP, SCRFD and ArcFace directly — no `insightface` package, which pulls in a large build
chain), `numpy`, `tokenizers` (CLIP tokenizer.json), `sqlite-vec` (pinned; vector distance
in SQL), `opencv-python-headless` (resize/warp for preprocessing and alignment, and the
YuNet/SFace fallback); `onnx` as a dev dependency to build tiny synthetic models in tests.
Models are fetched by `just models` into `<data_root>/models/`, never committed. Settings:
`docs/guides/settings.md` (Local ML). The model-format assumptions are written in
`adapters/onnx_clip.py` and checked against real models by `tests/ml/test_real_models.py`.

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
**Client library:** `httpx` (sync client; its `MockTransport` lets the adapter be tested with
no network and no model). Added 2026-09-29.

## Sources

| Source                       | Tool                                                                           | Status / caveats                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Local folder / external disk | direct                                                                         | Primary path, M1                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| MEGA                         | `rclone` mega backend                                                          | Works; rclone docs warn MEGA may block logins under heavy use → throttle (`--tpslimit`), pull once into staging                                                                                                                                                                                                                                                                                                                                                                         |
| Proton Drive                 | Proton's official `proton-drive` CLI (v0.9.0+), not rclone                     | Signs in through a browser on the machine and keeps its session in the system keyring, so the app never sees or stores the Proton password (rclone's reverse-engineered backend needs it, and cannot read the Photos section). Reads both the Photos section and "My files". We only ever build its list and download commands. It has no incremental copy, so the adapter keeps its own list of fetched items (`adapters/proton_drive.py`). Open: how long a session lasts unattended. |
| iPhone                       | `libimobiledevice` + `ifuse` (USB/Wi-Fi) or iCloud "Download originals" folder | Wireless ADB does not apply to iPhone                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Android                      | `adb pull /sdcard/DCIM` over wireless debugging                                | Could-have                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

All sources are **pull-only** into `staging/`; the import step is the same for all.

## Frontend: SvelteKit + TypeScript, static build, PWA

**Why:** small bundles and fast rendering on phones; one responsive codebase for laptop and
mobile; installable as a PWA (no app-store work). Built as static files served by FastAPI.

- Virtualised justified grid (own component, tested) — the core performance piece.
- No runtime dependencies at all (`web/package.json` has only `devDependencies`): everything
  below is our own code.
- Charts (calendar heat map, small multiples): hand-written SVG, no D3 and no chart kit with
  default chrome (see DESIGN_PRINCIPLES).
- Map: our own SVG. The land outline is one path generated from Natural Earth 1:110m
  (`web/scripts/make-world.ts` → `web/src/lib/world.ts`), so there are no tiles and no keys.
  MapLibre GL with a self-hosted PMTiles file was the plan and is not used.
- API client and types written by hand (`web/src/lib/api/client.ts`, `types.ts`) from
  `docs/contracts/api-v1.md`; a backend test checks every route in that contract exists
  (`tests/api/test_contract.py`). Not generated: `openapi-typescript` is not used.
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
Flow: `docs/ARCHITECTURE.md` (Album → print); routes: `docs/contracts/api-v1.md`.

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
**Upload parsing:** `python-multipart` (the parser FastAPI itself uses), driven as a _streaming_
parser so each file goes straight to `data/tmp`, hashed as it arrives and cut off at the size
limit, instead of being spooled whole to the system temp folder first. Added 2026-09-29.

## Concurrency, jobs and rendering (fix/backend, 2026-10-02)

No new dependency. Decisions, with the measurements in `PERFORMANCE.md`:

- **One `Database` per process** (`adapters/sqlite_database.py`): one writer connection and one
  lock shared by every store, per-thread read-only WAL connections for reads. Replaces one
  connection + RLock per store (several locks on one connection could interleave transactions).
- **Visibility as per-photo correlated SQL** instead of a whole-library CTE: a timeline page
  costs ~4 ms at 50k photos (was 160–200 ms).
- **Job lanes** (`app.worker.Lanes`): quick lane, long lane (imports, pulls, backups), preview
  pool of max(1, cores − 2) threads. Still one SQLite-backed queue; no APScheduler/Celery.
- **WebP effort 2** for derivatives (default 4): half the encode time, a few % more bytes.
- **GZip** (Starlette's middleware, level 6, ≥ 1 KiB, never images/ZIPs/PDFs/originals): the
  map keeps its contract shape and shrinks ~17× instead of changing the payload format.
- **One `Settings`** with nested sections (ml, ops, integrations) filled from the historical
  env names by one settings source; no `python-dotenv` import of our own (pydantic-settings
  already reads `.env`).

## Tooling

| Concern                  | Tool                                                                                                                                                                                                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Task runner              | `just`                                                                                                                                                                                                                                                                            |
| Python lint/format/types | ruff, ruff format, mypy strict (the whole package), pyright in editor OK                                                                                                                                                                                                          |
| Python tests             | pytest, hypothesis, pytest-cov, import-linter; PyYAML (reads `deploy/compose.yml` in the deploy tests); `httpx2` is the transport of Starlette ≥ 1.x's `TestClient` (with plain `httpx` it warns, an error under our warning filter) — kept on purpose (reviewed 2026-10-02, B20) |
| Web lint/format/types    | eslint, prettier, svelte-check, TypeScript strict                                                                                                                                                                                                                                 |
| Web tests                | Vitest in browser mode (`vitest-browser-svelte` on `@vitest/browser-playwright`), Playwright (E2E, mobile + desktop viewports), axe-core (`@axe-core/playwright`)                                                                                                                 |
| Pre-commit               | pre-commit (ruff, prettier + eslint, gitleaks, no large files)                                                                                                                                                                                                                    |
| CI                       | GitHub Actions (`.github/workflows/ci.yml`), on every pull request and on main: backend lint → layer contracts → types → tests → import smoke run; web lint → types → tests → build; gitleaks. No E2E step: `just e2e` and `just e2e-mock` run locally                            |
| Versioning               | Conventional Commits. No release tooling yet                                                                                                                                                                                                                                      |

## Typefaces (decided 2026-10-15)

**Inter** (Fontsource 5.3.0, upstream Inter v20, SIL OFL 1.1, "Copyright 2016 The Inter
Project Authors") for everything you read or operate, titles and data included (tabular
figures), for the Flight look. C delegated the choice. A variable font with a weight axis
(100–900) and an optical-size axis (14–32), so large titles get Inter's Display shapes without
a second family. Two upright woff2 files are vendored, latin and latin-ext
(`inter-latin-opsz-normal.woff2`, `inter-latin-ext-opsz-normal.woff2`), with the licence as
`Inter-OFL.txt`; no italic (only the Album theme's voice is italic, in Newsreader).

**Atkinson Hyperlegible Next** (variable weight 200–800, Braille Institute) becomes the Larger
text face: drawn for readers with low vision, it was the interface face from 2026-10-14 and
stays vendored for a per-account choice the look sheet does not have yet. Newsreader (serif,
optical sizes) stays as the title face of the Album theme. A command or path an admin reads
uses the system monospace.

All SIL Open Font License; the woff2 files (from Fontsource 5.3.0) and licences are vendored in
`web/static/fonts/`, served by the app itself — no font CDN, nothing fetched at runtime, and no
package: the fonts are static files, so "no runtime dependencies" still holds.
Fallbacks: the system sans, Iowan/Charter/Georgia.
Replaced Atkinson as the interface face (2026-10-15), which had replaced Hanken Grotesk and
Martian Mono (2026-10-08), which had replaced Instrument Sans (2026-10-02).
