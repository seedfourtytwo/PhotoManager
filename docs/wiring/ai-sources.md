# Wiring: AI socket, remote sources, phone/web upload (branch `feat/ai-sources`)

> **Historical integration record.** This page describes how a branch was wired in and is not
> kept up to date: file, class and migration names in it may be stale. For the settings see
> [`docs/guides/settings.md`](../guides/settings.md); for how the app is built today see
> [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).

> **Status (2026-10-02, fix/backend): wired.** Everything here runs in the app: `api/services.py`
> builds it from the one `Settings` and the one `Database`. This page stays as the record of how
> the branch was integrated; where it differs from the code, the code and ARCHITECTURE.md win.


## 1. What the branch adds

| Area | Files |
|---|---|
| Domain (pure) | `domain/album_plan.py`, `domain/remote_source.py`, `domain/uploads.py`; `domain/media_types.py` gains `IMPORTABLE_EXTENSIONS` (one appended constant) |
| Ports | `ports/ai.py` (+ `plan_album`, `AICall`, `AILog`), `ports/sync.py`, `ports/upload.py` |
| Adapters | `adapters/ollama_ai.py`, `adapters/rclone_sync.py`, `adapters/upload_spool.py`, `adapters/source_area_store.py`, `adapters/sqlite_integrations.py`; `adapters/null_ai.py` gains `plan_album` |
| Use cases | `app/sync_source.py`, `app/upload.py`, `app/devices.py` |
| API | `api/integration_settings.py`, `api/integrations.py`, `api/upload_stream.py`, `api/routes/upload.py`, `api/routes/remote_sources.py` |
| Migrations | `0030_ai_log.sql`, `0031_remote_sources_inbox_devices.sql` |
| Dependencies | `httpx`, `python-multipart` (runtime), recorded in `TECH_DECISIONS.md` |

## 2. Migrations: renumber

The runner applies every file numbered above `PRAGMA user_version`. Rename the two files to
the next free numbers **after** the core branch's migrations, keeping their order:

```
0030_ai_log.sql                          -> 00NN_ai_log.sql
0031_remote_sources_inbox_devices.sql    -> 00NN+1_remote_sources_inbox_devices.sql
```

Any dev database created on this branch is already at version 31 and would skip lower-numbered
core migrations: delete it (it holds synthetic data only). `0031` adds `source.config_json`,
tables `inbox(user_id, source_id)` and `device(...)`. `inbox.user_id` and `device.user_id` are
plain integers; once `user` exists, add the foreign keys in a later migration if wanted.

## 3. Dependencies

`backend/pyproject.toml` gains `httpx>=0.28.1` and `python-multipart>=0.0.32`. If `uv.lock`
conflicts with another branch, take theirs and run `cd backend && uv lock`.

## 4. `api/services.py`

Four changes. The importer must get the *source-area* store, or it refuses the staging and
inbox folders (they live inside the data root on purpose, so they move with it).

```python
from photo_assistant.api.integration_settings import IntegrationSettings
from photo_assistant.api.integrations import Integrations, build_integrations, with_source_areas

@dataclass
class Services:
    ...
    integrations: Integrations          # (1) new field

def build_services(settings: Settings) -> Services:
    ...
    repo = SqliteRepository(open_database(root / "library.db", backup_dir=root / "db-backups"))
    store = DiskLibraryStore(root)
    ...
    importer = ImportSource(
        ...,
        store=with_source_areas(store, root),          # (2) was: store=store
        ...
    )
    integrations = build_integrations(                 # (3)
        data_root=root,
        settings=IntegrationSettings(),
        conn=open_database(root / "library.db"),       # own connection; WAL lets both work
        repo=repo,
        importer=importer,
        clock=clock,
    )
    worker = Worker(
        repo,
        {
            PREVIEW_JOB: GeneratePreview(repo, store, renderer, settings.preview_edge),
            # (4) was: importer.run(...). SyncSource pulls rclone sources first and just
            # imports every other kind, so this one handler serves all scan jobs.
            SCAN_JOB_KIND: lambda payload: integrations.sync_source.run(int(str(payload["source_id"]))),
        },
        ...
    )
    return Services(..., integrations)
```

`Services.close()`: if `integrations.ai` is an `OllamaProvider`, call its `close()`.

**Job names:** no new job kinds. Uploads and `/api/remote-sources/{id}/pull` enqueue
`"scan_source"` (`app.sync_source.SCAN_JOB_KIND`);
`POST /api/sources/{id}/scan` and `scan-all` keep working and now pull remote sources too.

## 5. `api/main.py`

```python
from photo_assistant.api.routes import remote_sources, upload
...
for module in (system, sources, imports, assets, upload, remote_sources):
    app.include_router(module.router)

# in lifespan, after build_services:
app.state.integrations = services.integrations
```

## 6. Authentication (no hooks since fix/backend, B18)

The `app.state.session_user_hook` / `uploader_hook` pair is gone (it failed open when unset).
One dependency in `api/deps.py`, `session_or_device_user`, resolves the caller of
`/api/upload` and `/api/upload/check`:

1. `Authorization` header present → it must be `Bearer <device token>` of an unrevoked device
   whose account is active, else **401** (a bad token never falls back to the session).
2. Otherwise the `pa_session` cookie; none or expired → **401**.

`require_not_guest` (the same one used by albums, people and the share directory) then refuses
guests with **403**. Device management (`/api/devices`) is session-only (`session_only_user`).
An admin PIN reset revokes the user's device tokens. Tests sign in for real
(tests/api/test_upload_api.py).

## 7. Inbox privacy (needs core's access model)

Each user's inbox is a source of kind `"inbox"` created on first upload by
`SqliteInboxes.ensure_inbox_source(user_id, root)`. **Private to that user by default:** when
`source_access` exists, give a new inbox source `{everyone: null, users: [{user_id: <owner>,
level: "edit"}]}` (extend `SqliteInboxes._create`, or apply the default in core by
`kind == "inbox"` + the `inbox` table), and set `SourceOut.owner_id` from `inbox.user_id`.
Until then, the inbox is visible like any other source.

## 8. Settings (`IntegrationSettings`, env prefix `PA_`, same `.env`)

| Setting | Default | Meaning |
|---|---|---|
| `PA_UPLOAD_MAX_MB` | 200 | per-file limit; the upload is cut off as soon as it passes |
| `PA_UPLOAD_MAX_FILES` | 500 | per request |
| `PA_RCLONE_BINARY` | `rclone` | |
| `PA_PROTON_DRIVE_BINARY` | `proton-drive` | Proton's own CLI; also looked for in `~/.local/bin` |
| `PA_RCLONE_CONFIG` | unset (rclone's default file) | path to `rclone.conf` |
| `PA_RCLONE_TPSLIMIT` / `_TRANSFERS` / `_CHECKERS` | 4 / 2 / 4 | MEGA-safe throttling |
| `PA_RCLONE_TIMEOUT_HOURS` | 6 | a pull is stopped after this; rerun continues |
| `PA_AI_PROVIDER` | `none` | `ollama` to switch the AI socket on |
| `PA_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | the only host AI calls go to |
| `PA_OLLAMA_CAPTION_MODEL` / `_PLAN_MODEL` | unset | a capability is offered only if its model is set *and* pulled |
| `PA_OLLAMA_TIMEOUT_SECONDS` | 120 | |

`RCLONE_CONFIG_PASS` (rclone's own variable) in the service environment unlocks an encrypted
rclone config; it is inherited by the subprocess. The integrator may fold these fields into
`Settings`; `build_integrations` only needs the same attribute names.

Remote access for phones: add the LAN / Tailscale host name to `PA_ALLOWED_HOSTS` and bind
beyond 127.0.0.1 once login exists (M2). Shortcuts send no `Origin`/`Sec-Fetch-Site`, so the
cross-site guard lets them through; bearer requests can't be forged by a browser.

## 9. API additions (for docs/contracts/api-v1.md, by agreement)

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/upload` | session or device | multipart, any field name, many files | `{files: [{name, outcome: stored\|duplicate\|rejected, stored_as, content_hash, asset_id, reason}], import_job_id\|null}`; 400 broken multipart, 415 not multipart |
| POST | `/api/upload/check` | session or device | `{hashes: [blake3 hex]}` (≤ 5000) | `{missing: [...]}`; 422 malformed |
| GET | `/api/devices` | session | – | `[{id, name, platform, created_at, last_used_at, revoked}]` |
| POST | `/api/devices` | session | `{name, platform: ios\|android\|desktop\|other}` | `201 {device, token}` (token shown once) |
| DELETE | `/api/devices/{id}` | session | – | `204`; `404` if not yours |
| GET | `/api/remote-sources/remotes` | session (→ admin) | – | `{remotes: [name]}`; 503 no rclone |
| POST | `/api/remote-sources` | session (→ admin) | `{label, remote, path}` | `201 {id, label, remote, path}`; 422 unknown/unsafe remote |
| POST | `/api/remote-sources/{id}/pull` | session (→ admin) | – | `202 {job_id, source_id}` |

ARCHITECTURE §4 "Phone upload" names `/sync/check`; the built path is `/api/upload/check`
(plain multipart, not tus/resumable yet).

## 10. Behaviour worth knowing

- **Remote pulls** run `rclone copy remote:path data/staging/<id>` only; a test snapshots the
  "remote" before/after. Changed remote files are refreshed in staging (the importer keeps both
  versions); deleted ones stay. Login refused, folder not found and rate limiting are recorded
  as a failed import run (message in the import history) and the job completes, so the worker
  does not hammer MEGA; other errors are recorded and retried by the worker.
- **Uploads** are accepted by magic bytes (JPEG, PNG, GIF, WebP, TIFF-based RAW, HEIC/HEIF,
  AVIF, CR3, RAF, ORF, RW2); videos are refused for now. Names are reduced to one NFC path
  component; if the extension isn't a photo one, the sniffed one is appended.
- **AI** is never called unless `PA_AI_PROVIDER=ollama` and a model is set. Captions send a
  ≤1024 px JPEG with all metadata stripped. Every chat attempt goes to `ai_log`
  (prompt/answer truncated to 4000 chars, never image bytes). No retention policy yet.
- **Rclone sources' `root`** is absolute (`<data>/staging/<id>`), refreshed on every pull, so a
  moved data root heals itself; inbox roots heal on the next upload.

## 11. Docs to update on merge

FEATURES: 1.1b, 1.6 (built, needs wiring + UI), 7.2/7.3 (adapter built; no UI/use case yet),
10.2 (server side), 10.3 (upload + check + device tokens; not resumable), 10.4 (guide written,
spike on a real iPhone still to do). Guides: `docs/guides/cloud-sources.md`,
`docs/guides/iphone-shortcut.md`.
