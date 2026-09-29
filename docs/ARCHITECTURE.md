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
| `api/` | HTTP routes, auth, DTOs | `app` | API tests (httpx) |
| `web/` | UI | generated API client | component tests (Vitest), E2E (Playwright) |

Rule: dependencies point inward. `domain` never imports FastAPI, SQL, or a file path.
An import-linter check enforces this in CI.

## 3. Data model (first cut)

```
user(id, name, password_hash, role[admin|member|guest], created_at)
user_group(id, name);  user_group_member(group_id, user_id)
source_access(source_id, user_id NULL, group_id NULL, everyone BOOL, level[view|download|edit])
device(id, user_id, name, platform, last_sync_at, sync_cursor)   -- phone app installs

asset(id, blake3 UNIQUE, kind[photo|live|raw], mime, width, height, bytes,
      taken_at, taken_at_source[exif|xmp|filename|mtime], tz_offset,
      lat, lon, place_id, camera, lens, orientation, phash,
      library_path, imported_at, hidden_globally)

asset_source(asset_id, source_id, original_path, seen_at)       -- all places a file came from
source(id, kind[folder|rclone_remote|mega|proton|iphone|android], label, config_json,
       enabled, last_scan_at, last_scan_status)                 -- many sources, one library

edit_recipe(asset_id, user_id, recipe_json, updated_at)          -- rotate/crop/adjust; original untouched
backup_target(id, kind[local|rclone], label, repo_url, schedule_cron, retention_json, enabled)
backup_run(id, target_id, started_at, finished_at, status, snapshot_id, bytes_added, error)
export_job(id, user_id, scope_json, options_json, status, bytes_done, bytes_total, path)

derivative(asset_id, kind[thumb|preview], path, width, height)

user_asset(user_id, asset_id, favourite, hidden, private)       -- per-user state

tag(id, name, kind[auto|manual]);  asset_tag(asset_id, tag_id, score, by[user|model])
person(id, name, cover_face_id);   face(id, asset_id, bbox, embedding_rowid, person_id, quality)
place(id, country, region, city)

album(id, owner_id, title, description, cover_asset_id, theme_id, created_at)
album_member(album_id, user_id, role[owner|editor|viewer])
album_page(id, album_id, position, layout_id, caption)
album_slot(page_id, slot_index, asset_id, crop_json)            -- crop never alters the original
theme(id, name, tokens_json);  layout(id, name, slots_json)     -- data, not code

job(id, kind, payload_json, status, attempts, error, created_at, updated_at)
ai_log(id, capability, request_json, response_json, model, created_at)

vec_clip   USING vec0(embedding float[512])   -- rowid = asset.id
vec_face   USING vec0(embedding float[512])   -- rowid = face.id
```

Migrations: Alembic, one migration per PR that touches schema, always reversible in dev.

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
`ExportPhotos(scope, options)` resolves the scope (ids, date range, album, filter) to assets →
for each asset: original bytes, or `ImageRenderer.render(original, recipe, format, max_edge,
strip_meta)` via libvips → written into a **streamed ZIP** response (`zipstream`), so a
2 GB year export needs no temp space. Above a size threshold it becomes an `export_job` with
progress. Naming and folder layout are pure domain functions (unit-tested).

### Edit recipe
`EditRecipe` is a validated value object: `{rotate, flip, crop:{x,y,w,h in 0..1}, straighten,
adjust:{…}}`. The browser previews it (CSS transforms / canvas); the server renders it with
libvips for loupe previews and downloads. Golden-image tests keep preview and export in step.

### Backup
`BackupPort` with a restic adapter. Per target: `restic backup data/originals data/recipes
data/db-snapshot` where the DB snapshot is taken first with SQLite's online backup API (never
copy a live `.db` file). restic stores deduplicated, encrypted, versioned snapshots; its rclone
backend reaches SMB/SFTP/cloud targets. The scheduler (APScheduler in the worker) runs each
target's schedule, then `restic forget --prune` with the retention policy. Results go to a
`backup_run` table that feeds the status page and the overdue banner.

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

## 5. Performance budget (10k photos on the laptop)

| Operation | Budget |
|---|---|
| Timeline first paint (LAN, phone) | < 1.0 s |
| Scroll a month of thumbnails | 60 fps, no layout shift |
| Filter change | < 200 ms p95 |
| Semantic search | < 500 ms p95 |
| Full import + thumbnails of 10k photos | < 30 min |
| CLIP + faces for 10k photos on the RTX 2070 | < 1 h (CPU fallback: overnight OK) |

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

- Bound to LAN interface only; no public exposure; Tailscale for remote.
- Passwords: argon2id. Sessions: HTTP-only, SameSite=strict cookies.
- Source credentials live in rclone's own encrypted config, never in `library.db`.
- AI calls only go to the configured base URL; each request is logged in `ai_log`.
- **Visibility is one function in the repository layer:** `visible_assets(user)` = assets with
  at least one `asset_source` whose source grants the user access, ∪ assets in albums shared
  with the user, minus other users' private items. Every query goes through it; the UI never
  filters for security. Covered by a table-driven test of users × sources × albums.
- Download and edit endpoints check the access *level*, not just visibility.
