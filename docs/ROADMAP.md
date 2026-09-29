# Roadmap

Each milestone ends with the QA session in `ENGINEERING_RULES.md §7` and a tagged release.
Sizes are rough (S ≈ ½ day, M ≈ 1–2 days, L ≈ 3–5 days of focused work).
Test data for M1–M3: a folder of real photos already on the laptop/server, plus the committed
fixture set. Cloud and phone sources come in M4.

## M0 — Foundations (current)

Goal: a repo that makes doing the right thing the easy thing.

| Issue | Size |
|---|---|
| Create private GitHub repo `photo-assistant` (C's personal account), labels, GitHub Project board — **waiting on C** | S |
| ✅ Monorepo skeleton: `backend/` (uv, FastAPI), `web/` (SvelteKit, static), `justfile`, pre-commit | S |
| ✅ CI workflow (lint → layer contracts → types → tests → smoke run → build → gitleaks); branch protection once the repo exists | S |
| ✅ Import-linter layer + pure-domain contracts; mypy strict | S |
| ✅ "Originals untouched" guard fixture · ◻ full fixture photo set (generator started, needs HEIC/RAW/EXIF cases) | M |
| ~~Decide blocking open questions~~ (done 2026-09-29) | — |

**Done when:** `just setup && just check && just dev` works on a clean clone on the laptop.

## M1 — Library core (import from folders)

Goal: all photos from several folders in one de-duplicated, browsable-by-API library.

| Issue | Size |
|---|---|
| ✅ Domain: capture-time fallback chain (property tests) | M |
| ✅ Domain: dedup decision by BLAKE3; `asset_source` bookkeeping | S |
| ✅ Adapter: ExifTool reader (+ contract tests) | M |
| ✅ Adapter: libvips thumb/preview renderer incl. HEIC & orientation | M |
| ✅ SQLite schema v1 + Alembic + repository | M |
| ✅ Job queue table + worker + progress endpoint | M |
| ✅ **Multiple sources**: register/label/enable folders; rescan all | M |
| ✅ `ImportFolder` use case: idempotent, resumable, report | L |
| ✅ API: list assets (cursor pagination), asset detail, thumbnails | M |
| ✅ `AIProvider` port + `NullAIProvider` | S |
| ✅ Cross-cutting M1 items (FEATURES §11: disk guard, logs, pre-migration snapshot, worker limits, iPhone file quirks, video skip report) | M |

**Status: done 2026-09-29**, after two independent review rounds (first: 3 critical and 3
major findings; second, attacking the fixes: 1 major and 3 minor), all fixed with regression
tests. Real-data run on 200 of C's photos: every file
accounted for; import 84 ms/photo (≈ 14 min per 10k, budget 30); previews ≈ 0.2 s/photo in the
background; rescan of unchanged files 0.7 s.

**Acceptance:** import two overlapping test folders twice; second run adds 0 assets; source
folders byte-identical; report numbers add up; 10k-photo import within budget.

## M2 — Browse, share, download

Goal: C and partner use it on laptop and phone over LAN.

| Issue | Size |
|---|---|
| Account system (roles admin/member/guest), login, per-user favourites/hidden/private | M |
| **Per-source access lists** + `visible_assets` rule + access admin UI | L |
| Web shell: nav rail / bottom bar, dark & light tokens | M |
| Virtualised justified grid with date scrubber | L |
| **Loupe**: fullscreen, keyboard ← → Esc F I, swipe, two fading edge buttons, neighbour preload | M |
| Facet filters + keyword search | L |
| **Fix dates** for one or many photos (FEATURES 2.12) | M |
| Calendar heat map view | M |
| Manual albums, shared between users, drag reorder | L |
| **Download**: single, multi-select, day/month/year/album/filter scope → streamed ZIP (originals) | M |
| Near-duplicate/burst grouping; offline geocoding | M |
| Per-source overview page | S |
| **HTTPS via Tailscale certificates** (needed for iPhone web-app install, full screen, share sheet); trash; account safety (FEATURES §11) | M |
| PWA install; phone E2E; web upload (phone Photos picker, laptop files/folder) into the user's inbox | M |

**Acceptance:** 6 golden journeys pass on desktop + phone viewport; partner can log in on her phone and upload a photo from it.

## M3 — Smart library & basic edits

| Issue | Size |
|---|---|
| CLIP embeddings (ONNX, CUDA/CPU) + sqlite-vec; model benchmark on our photos | L |
| Natural-language search, "more like this" | M |
| Auto-tags; screenshot/document filter | M |
| Faces (YuNet+SFace default), clustering, naming, merge/split; People view | L |
| Map view (MapLibre + local tiles) | M |
| Smart collections (saved filters); small multiples; On this day | M |
| **Download formats & resize**: JPEG/PNG/WebP, long-edge presets, strip GPS, naming, folder layout | M |
| **Editor v1**: rotate, flip, crop with ratios, straighten — non-destructive recipes | L |

## M4 — More sources, albums you can print

| Issue | Size |
|---|---|
| rclone `SourceSync`: SFTP/SMB/WebDAV remote folders, MEGA, Proton (beta, with fallback) | L |
| iPhone pull (libimobiledevice) or iCloud export folder; Android ADB (Could) | M |
| **Upload API** (hash check, resumable upload into per-user inbox, per-device tokens) | M |
| **Apple Shortcuts auto-upload**: spike on iOS limits, then shared shortcut + setup guide | M |
| Themes + layout templates as data; auto-fit by aspect ratio | L |
| Page editor (swap, layout, crop-in-frame, captions) | L |
| Event-based album suggestions (time + place clustering) | M |
| Typst print export: trim sizes, bleed, fonts, resolution check; PDF golden tests | L |
| Background export jobs; standalone converter (Could) | M |

## M5 — AI socket live

| Issue | Size |
|---|---|
| Ollama adapter, settings page, connection test | M |
| Captions (vision model) as proposals | M |
| "Describe an album" → `AlbumPlan` JSON → validated → reviewable proposal | L |
| Model benchmark harness (fixed image set + prompts) | M |
| Editor v2 decision: colour adjustments + presets (only if preview/export parity is solid) | L |

## M6 — Home server

| Issue | Size |
|---|---|
| Docker Compose image; data volume; migration guide laptop → server | M |
| **Migration laptop → Ubuntu server**: `just export-library` / `just import-library`, tested end to end; laptop becomes a browser client | M |
| **Backup** (§9b): restic targets, schedules, retention, encryption, status page, restore test | L |
| Tailscale remote access (upload from anywhere); integrity check; tested full-restore guide | M |
| Slideshow / ambient mode | S |

## Later — Phone app (parked)

Full web parity in a Capacitor shell plus background sync. Parked until it is worth the Apple
Developer fee ($99/yr) or the 7-day re-signing chore; the Shortcuts route (M4) covers uploads.

## How work is distributed

Each issue is one PR, owned by one agent or person, and lands behind tests. Parallel agents
split by **area** (ingest · ui · print · ai), never two on the same module at once.
Suggested model use: the strongest model for architecture, domain rules, reviews and QA;
a faster model for well-specified UI components and adapters with contract tests already written.
