# Wiring the ops branch (feat/ops) into main

> **Status (2026-10-02, fix/backend): wired.** Everything here runs in the app: `api/services.py`
> builds it from the one `Settings` and the one `Database`. This page stays as the record of how
> the branch was integrated; where it differs from the code, the code and ARCHITECTURE.md win.

Since fix/backend: the backup store shares the app's `Database`; the periodic check only
*enqueues* `backup_due`, and backups, restore tests and source scans run on the long-job lane
(`app.worker.Lanes`), so previews never wait behind them; a local repository may not overlap
a source folder (and no source may overlap a repository).

Everything on `feat/ops` is new files plus the justfile/.gitignore; nothing in
`api/main.py`, `api/services.py`, `__main__.py`, `ports/__init__.py`,
`sqlite_repository.py` or existing migrations/routes was edited. These are the exact steps.

## 1. Migration

`adapters/migrations/0040_backup.sql` → rename to the next free number after main's last
migration (e.g. `0004_backup.sql`). It only creates `backup_target` and `backup_run`.

## 2. Settings

`api/ops_settings.py::OpsSettings` (same `PA_` prefix, same `.env`) holds:

| Field | Default | Meaning |
|---|---|---|
| `backup_enabled` | `true` | run due backups inside the server |
| `backup_poll_seconds` | `60` | how often to look for due backups |
| `backup_restore_sample` | `20` | photos per restore test |
| `backup_scratch_dir` | system temp | where restore tests unpack (must be outside the library) |
| `backup_key_dir` | `~/.config/photo-assistant/backup-keys` | keys the guided setup makes, one 0600 file per target (must be outside the library; on the server, a volume of its own) |
| `restic_binary` | `restic` | |
| `restic_cache_dir` | restic default | |

Either keep it separate (`OpsSettings()` next to `Settings()`), or copy the fields into
`Settings` and pass `settings` where `OpsSettings` is expected (the field names match).

## 3. Services (`api/services.py`)

```python
from photo_assistant.api.ops_services import OpsServices, build_ops_services

@dataclass
class Services:
    ...
    ops: OpsServices

    def close(self) -> None:
        self.worker.stop()
        self.ops.close()          # stops the periodic thread, closes its DB connection
        self.exiftool.close()
        self.repo.close()

def build_services(settings: Settings) -> Services:
    ...                                             # repo, store, importer as today
    ops = build_ops_services(root, OpsSettings(), queue=repo)   # after open_database (migrated)
    worker = Worker(
        repo,
        {
            PREVIEW_JOB: ...,
            SCAN_JOB_KIND: ...,
            **ops.backup.job_handlers(),           # "backup_run", "backup_restore_test"
        },
        clock,
        poll_seconds=settings.worker_poll_seconds,
    )
    return Services(settings, repo, store, importer, worker, exiftool, ops)
```

`build_ops_services` opens its own WAL connection to `library.db`; build it **after** the main
`open_database` so migrations have run.

## 4. Startup (`api/main.py` lifespan)

```python
services.repo.recover_interrupted_jobs()
if settings.worker_enabled:
    services.worker.start()
    services.ops.start()      # marks crashed backup runs failed, starts the periodic thread
```

`ops.start()` must only run in the server (not in CLI imports), like the worker.

**Periodic hook / trash purge.** `ops.periodic` is an `app.periodic.Periodic` with one task
(`"due backups"` → `BackupService.run_due`). When the trash (FEATURES 11.3) lands, add its
purge as a second task in `build_ops_services`:
`PeriodicTask("trash purge", 3600, trash.purge_expired)`.

## 5. Router

```python
from photo_assistant.api.routes import backup
for module in (system, sources, imports, assets, backup):
    app.include_router(module.router)
app.state.ops = services.ops        # in the lifespan, next to app.state.services
```

Endpoints: `GET/POST /api/backups`, `PATCH /api/backups/{id}` (`{enabled?, schedule?, quiet_window?, retention?}`, v1.3),
`POST /api/backups/{id}/run` and `/restore-test` (202, queued as jobs),
`GET /api/backups/{id}/runs?limit=`. Each target in `GET /api/backups` has
`needs_attention` → the overdue/failed banner (FEATURES 9b.7).

**Admin placeholder:** the router depends on `routes.backup.require_admin`, which currently
allows everything (acceptable only while bound to 127.0.0.1). When login lands, replace its
body with the real admin check, or `app.dependency_overrides[backup.require_admin] = admin`.

## 6. CLI (`__main__.py`)

```python
from photo_assistant.api import cli_ops

sub = parser.add_subparsers(dest="command")
...                                   # import, sources as today
cli_ops.register(sub)                 # export-library, verify-library, doctor, backup …
args = parser.parse_args(argv)
if (code := cli_ops.dispatch(args)) is not None:
    return code
```

Then the justfile recipes can call `python -m photo_assistant <cmd>` instead of
`python -m photo_assistant.api.cli_ops <cmd>` (optional; both work).

## 7. Docs to touch at merge

- FEATURES §9b: 9b.1–9b.8 built (status); 9.4 Docker Compose written, untested; 9.5
  partially covered by `verify-library`.
- README: link `docs/guides/`.
- CI (`ci/github-ci.yml`): `apt install restic rclone` so the restic integration tests run
  instead of being skipped.

## Known limits

- A manual backup queued from the API runs on the single job worker: a long first backup
  delays preview jobs until it finishes. Do the first (full) run from the CLI
  (`just backup run ID`), or give backups their own worker later.
- The Docker image has never been built (no daemon in the dev environment).
