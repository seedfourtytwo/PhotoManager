# Backups that survive an absent destination, and say so

Date: 2026-10-08. Area: `backup` (domain, app, adapters, api) and the admin UI.
First of three specs; the other two (source modes, tags and search) follow separately.

## Goal

The library is backed up in at least two places, a place that is not connected never blocks
or damages the others, and C sees a warning on any page when that stops being true.

## What exists and stays

- restic as the engine, several targets, run one after another (`BackupService.run_due`).
- Weekly restore test per target, banner on the admin page, run history per target.
- The Proton Drive copy of a local target (`mirror_path`, issue 14).
- `ensure_repository` refuses to create a repository when the parent folder is missing.

## Problems this fixes

1. **A repository can be created on the laptop's own disk.** When a disk is unplugged its
   mount folder often stays behind, empty. `ensure_repository` sees no repository, sees that
   the parent folder exists, and runs `restic init` there. The next backups then fill the
   laptop disk and report success.
2. **An absent destination is recorded as a failure** and is indistinguishable from a real
   one (wrong password, damaged repository).
3. **No retry until the next schedule slot.** `_is_due` counts the failed attempt, so a disk
   plugged in an hour after the nightly slot waits a day.
4. **Nothing checks that two places are healthy.** Each target is judged alone.
5. **The warning shows on the admin page only.**

## Design

### 1. A repository is created once

`init` runs only during guided setup (the first backup of a new target). `_backup` calls a
new engine method `probe(repo) -> bool` (`restic cat config`; exit 10 means not there) and
never `init`. A target with no successful run yet still goes through `ensure_repository`.

### 2. Skipped is its own result

`BackupRunStatus.SKIPPED = "skipped"`. When the probe says the repository is not there, or
restic reports the rclone remote unreachable, the run is recorded as skipped with a reason
that says what to do ("the disk Backup is not connected: plug it in, the backup starts by
itself"). The loop moves to the next target. Wrong password, lock, incomplete snapshot and
everything else stay `failed`.

`backup_run.status` is free text, so no migration is needed.

The mirror follows the same rule: `MirrorError` "backup folder not found" and a Proton CLI
with no network become skipped; a sign-in problem stays failed.

### 3. Catch up when it comes back

A skipped run does not count as an attempt. While the latest run of a target is skipped the
target is probed every 15 minutes (`SKIP_RETRY`); while it stays unreachable nothing new is
written, so history shows one skipped line per absence, not one per probe. When the probe
succeeds the backup runs at once if the target is overdue, otherwise at the next moment its
quiet window allows.

### 4. The two-places rule

Pure function in `domain/backup.py`:

`protection(statuses, now) -> Protection(places_ok, places_total, problems)`

- A **place** is an enabled target, or the Proton copy of one. The copy counts as a place
  because it survives the loss of the disk; the UI labels it "copy of <target>" because it
  does not survive a damaged repository.
- A place is **ok** when its last successful run is not overdue, its last run did not fail,
  and (targets only) its last restore test passed.
- `protected` is `places_ok >= 2`.

Problems, each with a message that says what to do:

| Condition | Severity |
|---|---|
| fewer than two places set up | warning |
| fewer than two places ok | alert |
| a place failed (not skipped) | alert |
| a place skipped and now overdue | warning |
| restore test failed | alert |
| recovery key not confirmed saved | warning |

A skipped place that is not yet overdue raises nothing: an unplugged disk is normal.

### 5. Where it shows

- `GET /api/backups/health` (admin): `protected`, `places_ok`, `places_total`, `problems`.
- A banner in the root layout for admins, on every page, built from that endpoint. One line
  for the worst problem, a link to the backup page. It cannot be dismissed; it goes when the
  problem does.
- Backup page: one row per place, the Proton copy as its own row under its target. Status
  dot with three states: ok, not connected since <date>, needs attention. A header line
  "Protected in 2 places" or "Only 1 place is up to date".
- History lists skipped runs in a quiet style, failed runs in the warning style.
- One structured log line per round: target, result, reason.

### Out of scope

- An alert that reaches C outside the app (email, phone). The machine is offline most of the
  time and no outbound channel exists; it needs a decision on channel and a new dependency.
  Known gap: if the app itself is stopped, nobody is warned.
- Changing the engine, making Proton a restic target, source modes, tags.

## Failure modes covered by tests

Domain (`tests/domain/test_backup.py`):
- `protection`: 0, 1, 2 places; one ok and one overdue; copy counts as a place; disabled
  target does not; skipped-not-overdue raises nothing; skipped-and-overdue warns; failed
  restore test alerts.
- catch-up rule: skipped is not an attempt; retry not before 15 minutes; inside and outside
  the quiet window; overdue overrides the window.

App (`tests/app/test_backup.py`, fake engine):
- an established target whose repository is gone is skipped and `init` is never called;
- a new target still gets its repository created;
- first target skipped, second still runs;
- repeated probes while absent write one run row;
- repository returns: the backup runs and the mirror follows;
- wrong password stays failed.

Adapter (`tests/adapters/test_restic_backup.py`, real restic on a temp folder):
- `probe` is false for an empty folder and true for a repository.

API and web: health endpoint shape and admin-only access; banner renders on a non-admin
route for an admin and not for a member; desktop and phone screenshots.
