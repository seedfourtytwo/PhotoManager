# Architecture

## 1. Shape of the system

One backend process, one web client, one folder of data. Heavy work runs in a background
worker in the same codebase. Nothing talks to the internet unless a user configures a source
or an AI endpoint.

```
                ┌────────────────────── laptop / home server ──────────────────────┐
 phone ─┐       │                                                                  │
 laptop ┼─HTTP─▶│  web (SvelteKit PWA, static build)                               │
 tablet ┘       │        │ JSON over HTTP (OpenAPI-typed client)                   │
                │        ▼                                                         │
                │  api (FastAPI) ──────▶ domain (pure Python, no I/O)              │
                │        │                    ▲                                    │
                │        ▼                    │ ports (interfaces)                 │
                │  worker (job queue in SQLite) ── adapters:                       │
                │        exiftool · libvips · onnxruntime · rclone · typst ·       │
                │        ollama (optional) · filesystem                            │
                │                                                                  │
                │  data/  library.db (SQLite + sqlite-vec)                         │
                │         originals/YYYY/MM/<blake3>.<ext>   (immutable copies)    │
                │         derived/thumb|preview/<blake3>.webp                      │
                │         staging/<source>/…   (rclone pulls land here)            │
                │         exports/<album>/…pdf                                     │
                └──────────────────────────────────────────────────────────────────┘
```

## 2. Layers (hexagonal / ports & adapters)

| Layer | Contains | May import | Tested with |
|---|---|---|---|
| `domain/` | Entities, value objects, pure rules (date fallback, dedup decision, layout fitting, album plan validation) | stdlib only | fast unit tests, property tests |
| `app/` | Use cases (`ImportFolder`, `BuildAlbum`, `ExportPdf`, `SearchPhotos`) orchestrating ports | `domain` | unit tests with in-memory fakes |
| `ports/` | `Protocol` interfaces: `MetadataReader`, `ImageRenderer`, `Embedder`, `FaceAnalyzer`, `SourceSync`, `PrintRenderer`, `AIProvider`, `Repository`, `Clock` | `domain` | — |
| `adapters/` | Real implementations of ports | anything | contract tests + integration tests against real tools |
| `api/` | HTTP routes, auth, DTOs, CLI; **composition root** (`services.py` picks the real adapters) | `app`, `adapters` (wiring only) | API tests (httpx) |
| `web/` | UI | generated API client | component tests (Vitest), E2E (Playwright) |

Rule: dependencies point inward. `domain` never imports FastAPI, SQL, or a file path.
An import-linter check enforces this in CI.

## 3. Data model

Built (numbered SQL migrations in `adapters/migrations/`; see TECH_DECISIONS). M1 + M2 core:
`0001`–`0012`; `0013` ai_log; `0014` remote sources, inboxes, devices; `0015` local ML (embeddings,
faces, people, tags); `0016` backups; `0017` (fix/backend) `asset.private_by`, foreign keys on
`inbox`/`device` (→ user, cascade) and `backup_run` (→ target, cascade), the partial index
`asset_live_timeline (taken_at DESC, id DESC) WHERE trashed_at IS NULL`, whole-second
`taken_at` and the removal of degenerate crops. `ANALYZE` runs after migrating, `PRAGMA
optimize` every 6 h. Upgrades are tested from v3 (M1) and v16 (M2) libraries with data.

```
user(id, username UNIQUE NOCASE, display_name, password_hash argon2id, role[admin|member|guest],
     disabled, created_at)
session(token_hash PK sha256, user_id, created_at, last_seen_at)      -- 30 days idle
login_failure(username, ip, at)                                       -- 10 per 15 min → 429

source(id, kind, label, root, enabled, owner_id, created_at)
source_access(source_id, user_id NULL=everyone, level 1 view|2 download|3 edit)
asset(id, content_hash UNIQUE, kind, mime_type, byte_size, width, height,
      taken_at, tz_offset_min, date_source[exif|exif_create|xmp|filename|file_mtime|manual],
      latitude, longitude, camera_make, camera_model, orientation,
      library_path, thumb_path, thumb_w, thumb_h, preview_path, variant_of, imported_at,
      first_source_id  -- where it was first found (informational; grants nothing)
      private, private_by  -- the marker (0017): hides it only from people who reach it
                           -- solely through the marker's own sources or albums
      place_id, phash, group_id, edit_version, trashed_at, trashed_by)
asset_source(asset_id, source_id, relative_path, seen_at, byte_size, mtime_ns, ctime_ns)
user_asset(user_id, asset_id, favourite, hidden)                      -- per-user state
place(id, country, region, city)                                      -- offline geocoding
album(id, owner_id, title, description, cover_asset_id, created_at, updated_at)
album_member(album_id, user_id, role[viewer|editor])                  -- owner is album.owner_id
album_item(album_id, asset_id, position)
edit_recipe(asset_id PK, recipe_json, updated_by, updated_at)         -- one per photo, shared
date_change(id, asset_id, old_taken_at, old_tz_offset_min, old_date_source, new_taken_at,
            changed_by, changed_at)
purged_hash(content_hash PK, purged_at)                               -- never re-imported
import_run(...), import_item(...), job(id, kind, payload_json, status, attempts, error, …)
inbox(user_id PK → user ON DELETE CASCADE, source_id UNIQUE)              -- 0014, FK 0017
device(id, user_id → user ON DELETE CASCADE, name, platform, token_hash UNIQUE sha256,
       created_at, last_used_at, revoked_at, last_sync_at, sync_cursor)  -- 0014, FK 0017
ai_log(id, capability, model, attempt, ok, duration_ms, error, request_json, response_json)
backup_target(id, label UNIQUE, kind[local|rclone], repository, password_file, schedule,
              quiet_window, retention_json, enabled, created_at)                     -- 0016
backup_run(id, target_id → backup_target ON DELETE CASCADE, kind, status, started_at, …)
ml_task, clip_embedding, face, person, tag, asset_tag, asset_ml_flag                 -- 0015
```

Still planned (later milestones, first cut):

```
user_group(id, name);  user_group_member(group_id, user_id)
export_job(id, user_id, scope_json, options_json, status, bytes_done, bytes_total, path)
album_page(id, album_id, position, layout_id, caption)
album_slot(page_id, slot_index, asset_id, crop_json)            -- crop never alters the original
theme(id, name, tokens_json);  layout(id, name, slots_json)     -- data, not code
```

The SQLite adapter is one `SqliteRepository` composed of per-area mixins
(`sqlite_accounts`, `sqlite_access`, `sqlite_library`, `sqlite_albums`, `sqlite_edits`,
`sqlite_enrich`, `sqlite_trash`). It and every other store (integrations, ML, backups) are built
on the process's ONE `Database` (`adapters/sqlite_database.py`, B16/B26): a single writer
connection behind a single lock for every write and transaction (transactions nest by joining
the outer one), and a read-only WAL connection per thread for reads, so reads never wait for a
write. A read inside a transaction uses the writer and sees its own rows. A source of any kind
(folder, rclone, inbox) is created by one method, `SourceRegistry.add_source`, with the access
the domain rule `default_source_access` gives its kind.

## 4. Key flows

### Import (idempotent)
1. `SourceSync` (rclone / libimobiledevice / adb / none) mirrors the source into `staging/`.
   Remote sources are only ever *read* (`rclone copy`, never `sync` or `move`).
2. `ImportFolder` walks staging or a local folder → for each file: hash (BLAKE3, streamed).
3. Hash known? → add an `asset_source` row, done. Unknown? → read metadata (ExifTool, in
   batches) → pick the capture time → render the thumbnail from the source (proves it decodes)
   → check free disk → copy (not move) into `originals/`, verify the hash, make it read-only →
   create the `asset`.
4. Enqueue `preview` (M1); later `embed`, `faces`, `geocode`, `phash` jobs.
5. The job queue is a table; the worker polls it; each job is retryable and safe to rerun.

### Multiple sources
Each `source` row is scanned independently (local path, or an rclone remote pulled read-only
into `staging/<source_id>/`). Because assets are keyed by content hash, the same photo found in
three sources is one asset with three `asset_source` rows — aggregation is a consequence of the
data model, not extra logic. "Rescan all" enqueues one scan job per enabled source.

### Download / convert
`Downloads` (app/downloads.py) takes the scope (ids, album or filter) resolved through the
visibility rule, keeps only photos with ≥ download → for each: the untouched library file, or
`ImageRenderer.render_variant(original, RenderSpec(recipe, format, max_edge, quality,
keep_metadata))` via libvips; location / all metadata are stripped by ExifTool on a temporary
copy in `data/tmp` (never on the library file) → a **streamed, stored ZIP** (`zipstream-ng`),
so a 2 GB year export needs no archive on disk. Skipped photos are counted in `X-Skipped`; a
photo that fails while the ZIP streams is left out and listed in a final `manifest.txt`.
Size estimates start from each photo's real bytes (calibrated factors, PERFORMANCE.md). Above a size threshold it becomes an `export_job` with
progress. Naming and folder layout are pure domain functions (unit-tested).

### Edit recipe
`Recipe` (domain/edit_recipe.py) is a validated value object: `{rotate, flip_horizontal,
flip_vertical, crop:{x,y,w,h in 0..1 of the rotated image}, straighten ±15}`; order: rotate →
flip → straighten (clockwise, keeping the largest same-aspect centre) → crop. Thumbnails and
previews with a recipe are rendered on first request and cached as
`derived/edited/<hh>/<hash>-<recipe key>-<kind>.webp`; image URLs carry `?v=<edit_version>`. The browser previews it (CSS transforms / canvas); the server renders it with
libvips for loupe previews and downloads. Golden-image tests keep preview and export in step.

### Backup
`BackupPort` with a restic adapter. Per target: `restic backup data/originals data/recipes
data/db-snapshot` where the DB snapshot is taken first with SQLite's online backup API (never
copy a live `.db` file). restic stores deduplicated, encrypted, versioned snapshots; its rclone
backend reaches SMB/SFTP/cloud targets. The scheduler (APScheduler in the worker) runs each
target's schedule, then `restic forget --prune` with the retention policy. Results go to a
`backup_run` table that feeds the status page and the overdue banner.

Guided setup (issue 3): `BackupPlaces` (mounted disks, rclone remotes, facts about one place)
feeds the pure rule `plan_backup` (fits? writable? same disk? another backup there?); `KeyVault`
makes the encryption key in a 0600 file outside the library and the owner must confirm keeping
a copy (`backup_target.key_saved_at`, migration `0018`). The recovery guarantee is the rule
`restore_proof_due`: a restore test after the first successful backup, then weekly, a day
after a failed one; a failed proof or an unconfirmed key raises the banner.

### Phone inbox
`data/inbox/<user>/` is served over WebDAV (per-user credentials, LAN/Tailscale only).
It is registered as a normal `source`; a file watcher (plus a periodic rescan as safety net)
imports new files. Files stay in the inbox after import (so the phone app's "already uploaded"
state stays correct); a setting can clear inbox files older than N days once they are
confirmed in the library *and* in a successful backup.

### Phone upload (M4)
The app asks `POST /sync/check {hashes}` → uploads only the missing ones (resumable, tus
protocol) into the user's inbox source → normal import. Server → phone uses a per-device
change cursor (`GET /sync/changes?since=…`) for the albums the device follows. Same REST API
the web uses. Apple Shortcuts posts to the same upload API. If a phone app is ever built (parked), it is the web UI in a Capacitor shell; only `DeviceBridge` (photo
library, background upload, save to Photos) has a native implementation.

### Search
Query → parser splits facets (`date:2023`, `person:Lea`, `place:France`) from free text →
SQL filters narrow candidates → free text is embedded by the CLIP text encoder → sqlite-vec
KNN within candidates → results ranked, paginated with a cursor.

### Album → print
`Album` (pages → slots → assets + crops) + `Theme` + `Layout`s → `PrintRenderer`
serialises to a Typst document + JSON inputs → `typst` compiles PDF with bleed and embedded
fonts → resolution check runs *before* compile and returns warnings to the UI.

### AI socket
```
class AIProvider(Protocol):
    def capabilities(self) -> set[Capability]: ...
    def caption(self, image: bytes, lang: str) -> Caption: ...
    def plan_album(self, prompt: str, context: LibrarySummary) -> AlbumPlan: ...
```
`NullAIProvider` returns "not available" and the UI hides AI affordances.
`OllamaProvider` calls `/api/chat` with JSON-schema constrained output; the response is parsed
into `AlbumPlan` (pydantic) and **validated by domain rules** (every asset exists, the user may
see it, layouts exist) before it is shown as a proposal. Invalid output → one retry → error.
The LLM never writes to the database directly.

### Jobs and lanes
The queue is the `job` table; `app.worker.Lanes` runs it on three kinds of threads (B24, C28):
the **quick lane** (one thread: geocode, group, purge, ML, edited renders), the **long lane**
(one thread: `scan_source` — rclone pulls and folder imports —, `backup_run`,
`backup_restore_test`, `backup_due`) and a **preview pool** (max(1, cores − 2) threads). Each
claims only its kinds, atomically, so a backup or a big import never starves previews and
uploads. The periodic thread only enqueues (`backup_due`, trash purge, nightly face clustering)
or runs cheap housekeeping (`PRAGMA optimize`, pruning finished jobs older than 7 days).
Domain errors (`domain/errors.py`) fail a job without retries; anything else is retried 3×.
ML jobs are planned only when their model files are installed.

## 5. Performance budget (10k photos on the laptop)

| Operation | Budget |
|---|---|
| Timeline first paint (LAN, phone) | < 1.0 s |
| Scroll a month of thumbnails | 60 fps, no layout shift |
| Filter change | < 200 ms p95 |
| Semantic search | < 500 ms p95 |
| Full import + thumbnails of 10k photos | < 30 min |
| CLIP + faces for 10k photos on the RTX 2070 | < 1 h (CPU fallback: overnight OK) |

Measured numbers (before/after the QA fixes): [`PERFORMANCE.md`](PERFORMANCE.md).

## 6. Deployment path

- **M1–M5 laptop:** library lives on the laptop in `~/PhotoAssistant/data/`. `just dev` / `just run`
  (uvicorn + static web build), systemd user service optional.
- **M6 Ubuntu server:** same code in Docker Compose; `data/` is a volume; Tailscale for remote
  access. The laptop then becomes a browser client only.
- **Portability rules (tested from M1):** every path in the database is *relative to the data
  root*; the data root is one setting; no machine-specific state lives outside `data/` except
  secrets in `.env`. Moving = stop, copy `data/` (rsync), set the path, start. A CI test copies a
  library to a new location and checks every asset still resolves.

## 7. Security & privacy

- Bound to 127.0.0.1 until login exists (M2); later LAN/Tailscale only, never public.
- Host allow-list (defeats DNS rebinding) and a cross-site guard (Sec-Fetch-Site / Origin)
  in front of every route; extra host names (Tailscale) are a setting.
- File names with control characters never reach ExifTool (its argument protocol can't escape
  a newline; found in the M1 review). Only absolute paths are passed, so no name reads as an option.
- One import at a time per library (OS file lock), each photo recorded in one transaction,
  jobs claimed atomically, so CLI + server can't corrupt each other.
- Login: pick your account, type its 4-digit PIN (stored as an argon2id hash in
  `user.password_hash`; the column keeps its old name). Ten wrong tries lock that account from
  that address for 15 minutes. A PIN is only as strong as that lock, so the app stays on the
  home network or Tailscale, never public. Sessions: HTTP-only, SameSite=strict cookies.
- Source credentials live in rclone's own encrypted config, never in `library.db`.
- AI calls only go to the configured base URL; each request is logged in `ai_log`.
- **Visibility is one function in the repository layer:** `visibility(viewer)` in
  `adapters/sqlite_library.py` gives two SQL pieces over the photo `a`: a condition (is it
  visible, and live or in the trash) and the viewer's level. A grant is a source that gives the
  user (or everyone) a level, a source the user owns (edit), or an album the user owns or is a
  member of (always `view`: download and edit only ever come from sources); admins have edit
  through every source. A private photo only counts grants through sources its marker
  (`private_by`) does not own — the marker keeps all of theirs, albums never reach it. Guests
  are capped at download. The condition is correlated `EXISTS` per photo (C25), so a timeline
  page stops at its `LIMIT` on the timeline index; admins get a cheaper check (only someone
  else's private photos need a look). Timeline, facets, calendar, map, albums, detail, images,
  downloads, uploads' hash check and ML candidates all use it; the UI never filters for
  security. Safety nets: `tests/api/test_visibility.py` (users × sources × albums × private ×
  roles × trash) and `tests/adapters/test_visibility_rule.py` (random libraries checked against
  the previous set-based rule).
- Sessions: random 256-bit token in the `pa_session` cookie (HttpOnly, SameSite=Strict, Secure
  over HTTPS); only its SHA-256 is stored. Every `/api` route except health, setup and login
  needs a session; source, scan, import, job, access-list and user routes are admin-only.
  Upload routes take the session **or** a device token through one fail-closed dependency
  (`api/deps.py`). Changing a PIN ends the user's other sessions; an admin reset ends all
  of them and revokes the user's device tokens. First-run setup and the last-admin rule are
  atomic (one `BEGIN IMMEDIATE` transaction each).
- Errors: one `DomainError` hierarchy (`domain/errors.py`) and one handler in `api/main.py`;
  every error body, the cross-site guard's included, is `{"detail": sentence}`.
- Download and edit endpoints check the access *level*, not just visibility.
