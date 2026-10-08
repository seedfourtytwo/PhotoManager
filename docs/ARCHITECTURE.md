# Architecture

## 1. Shape of the system

One backend process, one web client, one folder of data. Heavy work runs in a background
worker in the same codebase. Nothing talks to the internet unless a user configures a source
or an AI endpoint.

```
                ┌────────────────────── laptop / home server ──────────────────────┐
 phone ─┐       │                                                                  │
 laptop ┼─HTTP─▶│  web (SvelteKit PWA, static build)                               │
 tablet ┘       │        │ JSON over HTTP (hand-written typed client)              │
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
| `app/` | Use cases (`ImportFolder`, `BuildAlbum`, `ExportPdf`, `SearchPhotos`) orchestrating ports | `domain` | unit tests, mostly on the real `SqliteRepository` over an in-memory database with small fakes for outside tools; only backups have a full in-memory fake store (`tests/fakes_backup.py`) |
| `ports/` | `Protocol` interfaces: `MetadataReader`, `ImageRenderer`, `Embedder`, `FaceAnalyzer`, `SourceSync`, `PrintRenderer`, `AIProvider`, `Repository`, `Clock` | `domain` | — |
| `adapters/` | Real implementations of ports | anything | integration tests against real tools; one contract test so far (`tests/adapters/test_backup_store.py`: fake and SQLite backup store, same checks) |
| `api/` | HTTP routes, auth, DTOs, CLI; **composition root** (`services.py` picks the real adapters) | `app`, `adapters` (wiring only) | API tests (httpx) |
| `web/` | UI | hand-written API client and types (`web/src/lib/api/`, kept in step with `docs/contracts/api-v1.md` by hand) | component tests (Vitest), E2E (Playwright) |

Rule: dependencies point inward. `domain` never imports FastAPI, SQL, or a file path.
import-linter checks this (`uv run lint-imports`, part of `just check`): the layer order, and
that `domain`, `app` and `ports` import no framework, SQL, subprocess, imaging or ML library.
CI (`.github/workflows/ci.yml`) runs the same check on every pull request.

## 3. Data model

Built (numbered SQL migrations in `adapters/migrations/`; see TECH_DECISIONS). M1 + M2 core:
`0001`–`0012`; `0013` ai_log; `0014` remote sources, inboxes, devices; `0015` local ML (embeddings,
faces, people, tags); `0016` backups; `0017` (fix/backend) `asset.private_by`, foreign keys on
`inbox`/`device` (→ user, cascade) and `backup_run` (→ target, cascade), the partial index
`asset_live_timeline (taken_at DESC, id DESC) WHERE trashed_at IS NULL`, whole-second
`taken_at` and the removal of degenerate crops; `0023` gives ownerless sources to the first
admin (see Visibility in §7); `0026` keeps what the last global face-clustering pass saw
(`face_cluster_pass`, `face_cluster_mark`). `ANALYZE` runs after migrating, `PRAGMA
optimize` every 6 h. Upgrades are tested from v3 (M1) and v16 (M2) libraries with data.

```
user(id, username UNIQUE NOCASE, display_name, password_hash argon2id, role[admin|member|guest],
     disabled, created_at,
     failed_pins, locked_at)        -- wrong PINs since the last good sign-in; 30 → locked (0024)
session(token_hash PK sha256, user_id, created_at, last_seen_at)      -- 30 days idle
login_failure(username, ip, at)       -- 10 per account in 15 min → 429; pruned after a day

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
import_run(...), import_item(...), job(id, kind, payload_json, status, attempts, error, …,
    run_after, claimed_by, claimed_at)          -- 0022: retry time, owner and lease
inbox(user_id PK → user ON DELETE CASCADE, source_id UNIQUE)              -- 0014, FK 0017
device(id, user_id → user ON DELETE CASCADE, name, platform, token_hash UNIQUE sha256,
       created_at, last_used_at, revoked_at, last_sync_at, sync_cursor)  -- 0014, FK 0017
ai_log(id, capability, model, attempt, ok, duration_ms, error, request_json, response_json)
backup_target(id, label UNIQUE, kind[local|rclone], repository, password_file, schedule,
              quiet_window, retention_json, enabled, created_at)                     -- 0016
backup_run(id, target_id → backup_target ON DELETE CASCADE, kind, status, started_at, …)
ml_task, clip_embedding, face, person, tag, asset_tag, asset_ml_flag                 -- 0015
face_cluster_pass(model PK, rule)   -- settings of the last finished global clustering pass (0026)
face_cluster_mark(face_id PK → face ON DELETE CASCADE, person_id, cluster_state, created_at,
                  fingerprint)      -- each face as that pass saw it (0026)
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
write. A read inside a transaction uses the writer and sees its own rows.

**Commits are not flushed one by one.** The writer runs with `synchronous = NORMAL`: in WAL
mode that cannot corrupt the database, and SQLite flushes the disk at checkpoints instead of
at every commit (3.0 ms → 0.03 ms per commit, see `PERFORMANCE.md`). The price is that a power
cut can take back the commits of the last seconds (until the operating system has written
them out, about half a minute at most on Linux). What is lost that way comes back by itself:
an import scans its folder again and finds the copied original by its hash, a queued job is
queued again by its periodic task or the next scan, an upload's inbox is picked up by the
hourly check. A change a person made in those seconds (a favourite, an album edit) has to be
made again. Three writes that nothing would redo are flushed before they return
(`Database.durable`): forgetting a purged photo, because its files are deleted right after;
a new backup target, the only link between a repository and its key file; and the owner's
confirmation that the key is kept. A source of any kind
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
5. The job queue is a table; the worker polls it; each job is retryable and safe to rerun
   ("Jobs and lanes" below: retries wait, running jobs have an owner).

**A file that changed in place** (a cut-off download later replaced by the whole file): the
path's `asset_source` row goes to the photo the file holds now. The photo it held before is
kept as long as another file holds it; if none does, the import moves it to the trash
(`trashed_by` empty: not a person's act) and says so on the report item, because a photo
without a source is hidden from every member while an admin keeps seeing it. From the trash it
can be restored for 30 days (it then has no source: only admins see it, or an album shares
it). If a file shows that content again, the import takes the photo back out; and purging it
does not put its hash on the never-import-again list, which is for what a person deleted.

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
Size estimates start from each photo's real bytes (calibrated factors, PERFORMANCE.md).
Every download is streamed in the request; a background `export_job` with progress for very
large exports is not built (it is in the planned tables of §3). Naming and folder layout are
pure domain functions (unit-tested).

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
copy a live `.db` file); what a crash left half-written (`*.partial`) is excluded. restic stores deduplicated, encrypted, versioned snapshots; its rclone
backend reaches SMB/SFTP/cloud targets. There is no scheduler library: the periodic thread
(`app/periodic.py`, one thread that runs each of its tasks every so many seconds) queues a
`backup_due` job every `PA_BACKUP_POLL_SECONDS` (60 s); that job, on the worker's long lane,
runs every target whose schedule says it is due and that is outside its quiet window, then
`restic forget --prune` with the target's retention policy. Results go to a `backup_run` table
that feeds the status page and the overdue banner.

Guided setup (issue 3): `BackupPlaces` (mounted disks, rclone remotes, facts about one place)
feeds the pure rule `plan_backup` (fits? writable? same disk? another backup there?); `KeyVault`
makes the encryption key in a 0600 file outside the library and the owner must confirm keeping
a copy (`backup_target.key_saved_at`, migration `0018`). The recovery guarantee is the rule
`restore_proof_due`: a restore test after the first successful backup, then weekly, a day
after a failed one; a failed proof or an unconfirmed key raises the banner.

### Phone inbox
`data/inbox/<user id>/` is each user's inbox: a normal `source`, private to its owner by
default. Files only arrive through the upload API below (there is no WebDAV share and no file
watcher); each upload request queues one import of that inbox. A safety net runs every hour
for a file whose request died before that: it queues an import only for an inbox that got a
file since its last import started (or whose last import did not finish), so an unchanged
inbox adds nothing to the import history. Files stay in the inbox after import. Not built:
clearing old inbox files.

### Phone upload
The client asks `POST /api/upload/check {hashes}` which ones this user lacks, then sends them
with `POST /api/upload` as ordinary multipart. The body is parsed as it streams
(`api/upload_stream.py`): each file goes straight to `data/tmp`, is hashed on the way and cut
off at `PA_UPLOAD_MAX_MB`, then moved into the inbox, and one import is queued. An upload is
not resumable (no tus): a broken request is sent again, and files that already arrived are
kept. The caller is a browser session or a per-device token (`/api/devices`), which is what
Apple Shortcuts uses. Not built: the server → phone change cursor (the `device.sync_cursor`
column exists, no route uses it). If a phone app is ever built (parked), it is the web UI in
a Capacitor shell; only `DeviceBridge` (photo library, background upload, save to Photos)
would have a native implementation.

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
    def capabilities(self) -> frozenset[Capability]: ...
    def caption(self, image: bytes, lang: str) -> str: ...
    def plan_album(self, prompt: str, context: LibrarySummary) -> AlbumPlan: ...
```
`NullAIProvider` returns "not available" and the UI hides AI affordances.
`OllamaProvider` calls `/api/chat` with JSON-schema constrained output; the response is parsed
into `AlbumPlan` (a frozen dataclass in `domain/album_plan.py`) and **validated by domain rules** (every asset exists, the user may
see it, layouts exist) before it is shown as a proposal. Invalid output → one retry → error.
The LLM never writes to the database directly.

### Jobs and lanes
The queue is the `job` table; `app.worker.Lanes` runs it on three kinds of threads (B24, C28):
the **quick lane** (one thread: geocode, group, purge, ML, edited renders), the **long lane**
(one thread: `scan_source` — rclone pulls and folder imports —, `backup_run`,
`backup_restore_test`, `backup_due`) and a **preview pool** (max(1, cores − 2) threads). Each
claims only its kinds, atomically, so a backup or a big import never starves previews and
uploads. The periodic thread only enqueues (`backup_due`, trash purge, nightly face clustering,
and a `scan_source` for each source whose automatic re-check is due: `app/recheck.py`, rule in
`domain/recheck.py`) or runs cheap housekeeping (`PRAGMA optimize`, pruning finished jobs older than 7 days).
ML jobs are planned only when their model files are installed. The global face-clustering
pass (nightly and at every start) looks only at waiting faces near a face that changed since
the last finished pass; what that pass saw is kept in the library (0026), so a restart goes
on from it. Every waiting face is stepped again only when no pass has finished yet for the
face model with the current clustering settings.

**Retries wait (0022).** Domain errors (`domain/errors.py`) fail a job at once, without
retries: they say "the same job would fail the same way" (a folder that is gone, a tool or a
model that is not installed, a backup target deleted meanwhile). So an error that may pass by
waiting must never be a `DomainError`: `SyncError`, `BackupError` and `AIUnavailableError`
stay outside the hierarchy for that reason (`tests/app/test_job_failures.py` pins both lists).
A pull fails for both kinds, so `SyncError` is split: by itself (network, a throttling or slow
provider, out of time) it is retried; its subclasses for what waiting cannot fix are a
`DomainError` too and fail the job at once (`SyncAuthError`, `SyncNotFoundError`,
`SyncToolMissingError`, `SyncUnsupportedError`, `SyncDiskFullError`: `ports/sync.py`).
Anything else gets 4 attempts (`domain/job_queue.MAX_ATTEMPTS`: one more than the schedule
has waits), and a failed attempt sets the job's `run_after`: 1 minute after the first failure,
5 after the second, 25 after the third (`RETRY_DELAYS`). A claim skips jobs whose time has
not come, so a network blip, a locked backup repository or an unplugged disk has ~31 minutes to
pass before the job fails for good, instead of ~3 seconds. "Retry" on the admin screen clears
the wait and the attempts: the job runs at the next poll. `run_until_idle` (CLI import, tests)
returns once nothing is *due*; a waiting retry stays queued for the server's worker.
`GET /api/jobs` rows carry `run_after`; `GET /api/stats` counts those jobs as `waiting`, apart
from `queued`, so screens that wait for "nothing queued or running" do not sit through it.

**Every process owns what it runs (0022).** The server and CLI commands share the table. Each
process claims under an owner id made at its start (`server-<pid>-<random>`, `cli-…`) and the
claim records `claimed_by` and `claimed_at`. While a handler runs, a small thread renews
`claimed_at` every 30 s (`HEARTBEAT_INTERVAL`) — independent of the job, so a backup of hours
stays fresh as long as its process lives. A running job whose claim is older than 5 minutes
(`CLAIM_STALE_AFTER`, ten missed heartbeats) belonged to a process that died:
`app.worker.StaleJobSweep` queues it again at server start and every minute from the periodic
thread. A fresh claim is never touched, whoever owns it, so a server start no longer restarts
the previews a running `import` command is working on; and a killed CLI command's job is
picked up after at most ~6 minutes without a server restart. The interrupted run stays counted
in `attempts`: a job that kills every process running it is failed, not run, once its attempts
are used up (the crash-loop guard). Two consequences to know: after a crash the server waits
those ~5 minutes before rerunning what it was doing, and after the machine slept (every claim
looks old, also live ones) the first sweep changes nothing — heartbeats come within 30 s and
the next sweep decides.

**Indexes (0022).** `job_waiting (kind, id) WHERE status = 'queued'` holds only waiting jobs:
each lane's poll and `enqueue_once` seek to their own kinds instead of walking the 10k previews
queued by an import. `asset_by_variant_of` serves the purge's variant lookup and the foreign-key
check on every `DELETE FROM asset`; `album_by_cover` (0025) does the same for album covers.

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
  secrets in `.env`. Moving = stop, copy `data/` (rsync), set the path, start. A test
  (`tests/app/test_library_transfer.py`) copies a library to a new location and checks it
  works there.

## 7. Security & privacy

- Bound to 127.0.0.1 by default (`PA_HOST`). Login exists, but the app still stays on
  loopback: other devices come in through Tailscale (`tailscale serve` in front of the port;
  the Docker image listens inside its container and compose publishes the port on the
  server's loopback only). Never public.
- Host allow-list (defeats DNS rebinding) and a cross-site guard (Sec-Fetch-Site / Origin)
  in front of every route; extra host names (Tailscale) are a setting.
- File names with control characters never reach ExifTool (its argument protocol can't escape
  a newline; found in the M1 review). Only absolute paths are passed, so no name reads as an option.
- One import at a time per library (OS file lock), each photo recorded in one transaction,
  jobs claimed atomically, so CLI + server can't corrupt each other.
- Login: pick your account, type its 4-digit PIN (stored as an argon2id hash in
  `user.password_hash`; the column keeps its old name). Wrong PINs are counted per account,
  from all addresses together: ten within 15 minutes make that account wait out the window
  (`429`), and thirty since its last good sign-in lock it (`423`) until an admin unlocks it or
  it gets a new PIN (People → Reset PIN, or `just set-pin` on the server, which is the way back
  for an only admin). The lock is on the user row, so a restart or the daily pruning of
  `login_failure` does not lift it. A try is counted in one transaction before the PIN is
  checked, so parallel guesses queue. A PIN is only as strong as these limits, so the app stays
  on the home network or Tailscale, never public. Anyone who can reach the sign-in screen can
  lock an account on purpose; that is the price of the limit. Sessions: HTTP-only,
  SameSite=strict cookies.
- Source credentials live in rclone's own encrypted config, never in `library.db`.
- AI calls only go to the configured base URL; each request is logged in `ai_log`.
- **Visibility is one function in the repository layer:** `visibility(viewer)` in
  `adapters/sqlite_library.py` gives two SQL pieces over the photo `a`: a condition (is it
  visible, and live or in the trash) and the viewer's level. A grant is a source that gives the
  user (or everyone) a level, a source the user owns (edit), or an album the user owns or is a
  member of (always `view`: download and edit only ever come from sources); admins have edit
  through every source. A private photo only counts grants through sources its marker
  (`private_by`) does not own — the marker keeps all of theirs, albums never reach it. That
  comparison needs an owner on the source, so every source has one: a folder or cloud (rclone,
  Proton Drive) source belongs to the admin who adds it, an upload inbox to its user, a folder
  imported from the command line to the first admin; migration `0023` gave the ownerless
  cloud sources of older libraries to the first admin. Only a library with no admin yet
  has ownerless sources; they go to the first admin when one is made, by the first-run setup
  or by `create-user --role admin` (`Accounts.give_ownerless_sources_to_first_admin`). Guests
  are capped at download. The condition is correlated `EXISTS` per photo (C25), so a timeline
  page stops at its `LIMIT` on the timeline index; admins get a cheaper check (only someone
  else's private photos need a look). Timeline, facets, calendar, map, albums, detail, images,
  downloads, uploads' hash check and ML candidates all use it; the UI never filters for
  security. Safety nets: `tests/api/test_visibility.py` (users × sources × albums × private ×
  roles × trash) and `tests/adapters/test_visibility_rule.py` (random libraries checked against
  the previous set-based rule).
- Sessions: random 256-bit token in the `pa_session` cookie (HttpOnly, SameSite=Strict, Secure
  over HTTPS); only its SHA-256 is stored. A session ends 30 days after its last use; the
  browser counts the cookie's 30 days from when it was set, so a session in use gets the same
  cookie again every 15 days (`api/security.SessionCookieRenewal`). The server cannot see a
  cookie's age: a second cookie, `pa_session_fresh`, is set alongside for 15 days, and a
  request without it is the sign that half the time is over. Every `/api` route except health, setup and login
  needs a session; source, scan, import, job, access-list and user routes are admin-only.
  Upload routes take the session **or** a device token through one fail-closed dependency
  (`api/deps.py`). Changing a PIN ends the user's other sessions; an admin reset ends all
  of them and revokes the user's device tokens. First-run setup and the last-admin rule are
  atomic (one `BEGIN IMMEDIATE` transaction each).
- Errors: one `DomainError` hierarchy (`domain/errors.py`) and one handler in `api/main.py`
  that turns any of them into its status and `{"detail": sentence}`. Six families carry the
  status: `DomainError` (400), `ForbiddenError` (403), `NotFoundError` (404), `ConflictError`
  (409), `InvalidError` (422), `UnavailableError` (503); the three sign-in errors set their own
  (401, 423, 429). A use case or adapter raises a named subclass with the sentence the user
  reads (`PersonNotFoundError`, `InvalidBackupTargetError`, `SourceExistsError`), and the route
  does nothing. Of the 83 exception classes, 55 are in the hierarchy (2026-10-08). Classes that
  were plain `ValueError`s before keep `ValueError` as a second base, so the command line and
  older `except ValueError` code still catch them.
  - **Outside on purpose (28 classes, each listed with its reason in
    `tests/unit/test_error_hierarchy.py`, which fails for a new class that is neither):**
    what may pass by waiting (`SyncError`, `BackupError`, `AIUnavailableError`: see "Retries
    wait"; a `SyncError` met while answering a request is a 503 from a second, two-line
    handler in `api/main.py`), signals caught where they are raised (`DuplicateAssetError`, `ToolMissingError`,
    `UploadTooLargeError`), and errors only the command line reports.
  - **Routes that still translate by hand (7 blocks):** a blocked print
    (its body also lists the photos); three whose sentence is the route's, not the error's
    (wrong current PIN, unknown backup target, photo not analysed yet); a too-long name on a
    people split (a bare `ValueError`, because the rename route lets the same error through
    as a 500); and two errors from libraries (pydantic in downloads, python-multipart in
    uploads).
  - Every error body, the cross-site guard's included, is `{"detail": sentence}`.
- Download and edit endpoints check the access *level*, not just visibility.
