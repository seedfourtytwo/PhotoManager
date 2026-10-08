# Backup Reachability and Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backup place that is not connected is skipped and caught up later, the app knows whether two places are healthy, and an admin sees a warning on every page when they are not.

**Architecture:** The rules (what counts as a healthy place, when to retry) are pure functions in `domain/backup.py`. `BackupService` asks the engine and the mirror "are you there?" before working and records `skipped` instead of `failed`. A new read-only endpoint feeds one banner in the web root layout.

**Tech Stack:** Python 3 (FastAPI, pytest, restic via subprocess), SvelteKit 2 / Svelte 5 (vitest, Playwright).

**Spec:** `docs/superpowers/specs/2026-10-08-backup-reachability-alerts-design.md`

## Global Constraints

- Read `AGENTS.md`, `docs/ENGINEERING_RULES.md`, `docs/DESIGN_PRINCIPLES.md` first.
- TDD: failing test first, confirm it fails for the right reason, then code.
- `domain/` is pure: stdlib only, no I/O. Layering is enforced by import-linter.
- No new dependency. No database migration (`backup_run.status` is free text).
- Never write to, move or delete a source file or a library original.
- `restic init` may only happen for a target that has never had a successful backup.
- User-facing messages say what happened and what to do, in plain words.
- No real photos anywhere; tests use the synthetic fixtures and the fakes in `backend/tests/fakes_backup.py`.
- Do not weaken a test, lower coverage or skip a check to get green.
- `just check` (from the repo root) must pass before every commit. Conventional Commits.
- Constants: `SKIP_RETRY = timedelta(minutes=15)`; a place is protected when `places_ok >= 2`.

Paths below: `B` = `backend/src/photo_assistant`, `T` = `backend/tests`, `W` = `web/src`.

---

### Task 1: Domain rules

**Files:**
- Modify: `B/domain/backup.py`
- Test: put the new tests beside the existing pure tests for `domain/backup.py` (find them with `grep -rl "plan_backup\|restore_proof_due" backend/tests`); if none exist create `T/unit/test_backup_protection.py`.

**Interfaces — Produces:**

```python
class BackupRunStatus(StrEnum):  # add one member
    SKIPPED = "skipped"  # the place was not connected; nothing was attempted

SKIP_RETRY = timedelta(minutes=15)

def backup_due(schedule: Schedule, last_attempt: datetime, now: datetime,
               window: QuietWindow | None, *, catching_up: bool) -> bool: ...
def probe_allowed(last_probe: datetime | None, now: datetime) -> bool: ...

# TargetStatus gains two fields, both defaulted so existing constructors keep working:
#   skipped_since: datetime | None = None   # start of the latest backup run when it is skipped
#   mirror_overdue: bool = False            # the copy has no fresh success

class Severity(StrEnum):
    ALERT = "alert"
    WARNING = "warning"

@dataclass(frozen=True, slots=True)
class Problem:
    severity: Severity
    message: str
    target_id: int | None = None

@dataclass(frozen=True, slots=True)
class Protection:
    places_ok: int
    places_total: int
    problems: tuple[Problem, ...]   # alerts first, then warnings, each in target order
    @property
    def protected(self) -> bool: return self.places_ok >= 2

def protection(statuses: Sequence[TargetStatus]) -> Protection: ...
```

Rules:

- `backup_due`: `is_due(schedule, last_attempt, now, window)`, or, when `catching_up`, `is_due(schedule, last_attempt, now, None)` (an overdue place that just came back does not wait for its quiet window).
- `probe_allowed`: true when `last_probe is None` or `now - last_probe >= SKIP_RETRY`.
- `protection` looks only at statuses whose `target.enabled` is true.
  - Each enabled target is a place. It is ok when `last_success_at is not None and not overdue and not failing and not restore_failing`.
  - Each enabled target with `target.mirror_path` adds a second place, the copy. It is ok when `last_mirror_at is not None and not mirror_overdue and not mirror_failing`.
  - Problems, in this order per target, alerts sorted before warnings overall (stable):

| Condition | Severity | Message |
|---|---|---|
| `places_total == 0` | warning | `No backup is set up: the photos exist only on this computer. Add two backup places.` |
| `places_total == 1` | warning | `Only one backup place is set up: add a second, so one lost disk is not the end of the photos.` |
| `places_total >= 2 and places_ok < 2` | alert | `Only {places_ok} of {places_total} backup places is up to date.` |
| `failing` | alert | `{label}: the last backup failed: {last_run.error or 'no reason given'}` |
| `restore_failing` | alert | `{label}: the last restore test failed. Open Backups and run it again.` |
| `mirror_failing` | alert | `{label}: the copy on Proton Drive failed: {mirror_error}` |
| `skipped_since is not None and overdue` | warning | `{label} has not been connected since {skipped_since:%d %b %Y}: connect it and the backup starts by itself.` |
| `overdue and skipped_since is None and not failing` | warning | `{label}: the backup is overdue.` |
| `mirror_overdue and not mirror_failing` | warning | `{label}: the copy on Proton Drive is out of date; it catches up when this computer is online.` |
| `key_unsaved` | warning | `{label}: the recovery key is not saved yet. Without it this backup cannot be read.` |

  - A target that is skipped but not overdue raises nothing.

- [ ] **Step 1: Write the failing tests.** One test per row above plus:
  `test_two_fresh_places_are_protected_and_raise_nothing`,
  `test_a_copy_on_proton_counts_as_a_second_place`,
  `test_a_disabled_target_is_not_a_place`,
  `test_a_skipped_place_that_is_not_overdue_raises_nothing`,
  `test_alerts_come_before_warnings`,
  `test_a_skipped_run_is_retried_only_after_fifteen_minutes` (14 min 59 s false, 15 min true, `None` true),
  `test_catching_up_ignores_the_quiet_window_and_a_normal_run_does_not`,
  `test_nothing_is_due_before_the_next_slot_even_when_catching_up`.
  Build `TargetStatus` values directly with a small local factory `status(label="Disk", **overrides)` that fills a `BackupTarget` (id from a counter, `enabled=True`, `key_saved_at` set, `schedule="daily 02:30"`) and `last_success_at` set, so each test changes only what it is about.
- [ ] **Step 2: Run them, confirm they fail** on the missing names: `cd backend && uv run pytest <test file> -q`.
- [ ] **Step 3: Implement** in `B/domain/backup.py` exactly the interfaces above. Update the `needs_attention` docstring only if its wording becomes wrong; do not change its logic.
- [ ] **Step 4: Run** the test file, then `just check`.
- [ ] **Step 5: Commit** `feat(backup): rules for skipped places and two-place protection`.

---

### Task 2: Ask the engine and the mirror "are you there?"

**Files:**
- Modify: `B/ports/backup.py`, `B/adapters/restic_backup.py`, `B/adapters/proton_mirror.py`, `T/fakes_backup.py`
- Test: `T/adapters/test_restic_backup.py`, the existing Proton mirror adapter test file (`grep -rl ProtonMirror backend/tests`)

**Interfaces — Produces:**

```python
# ports/backup.py
class BackupEngine(Protocol):
    def probe(self, repo: RepositoryRef) -> str | None:
        """None when the repository can be opened. Otherwise why it is out of reach right
        now (disk not plugged in, server not reachable). Never creates anything. Raises
        BackupError for problems waiting will not fix: wrong password, unreadable password
        file, a lock, restic not installed."""

class RepositoryMirror(Protocol):
    def probe(self, repository: Path, remote_folder: str) -> str | None:
        """None when a mirror run can start. Otherwise why not right now (backup folder not
        there, Proton Drive not reachable). Raises MirrorSignInError when not signed in and
        MirrorError when the remote folder is gone."""
```

`ResticBackup.probe`:

```python
def probe(self, repo: RepositoryRef) -> str | None:
    try:
        self._run(repo, ["cat", "config"])
    except RepositoryNotFoundError as exc:
        return str(exc)
    except (WrongPasswordError, PasswordFileError, RepositoryLockedError, BackupToolMissingError):
        raise
    except BackupError as exc:
        # a remote that does not answer has no exit code of its own; a local one that fails
        # any other way is a real fault
        if target_kind(repo.location) is TargetKind.RCLONE:
            return str(exc)
        raise
    return None
```

`ProtonMirror.probe`: return `f"backup folder not found: {repository}"` when `not repository.is_dir()`; then run `self._drive.run(["filesystem", "list", remote_folder, "--json"], _QUICK, remote_folder)`; map `SyncAuthError` → raise `MirrorSignInError(str(exc))`, `SyncNotFoundError` → raise `MirrorError(str(exc))`, any other `SyncError` → `return str(exc)`; else `None`. Leave `mirror()` as it is.

Fakes: `FakeEngine` gets `absent: str | None = None`; `probe` appends `"probe"` to `calls`, raises `self.fail["probe"]` if set, returns `self.absent`. `FakeMirror` gets `absent: str | None = None` and a `probe` that returns it (raising `self.fail` if set, the same way its `mirror` does). Read both fakes first and match their style.

- [ ] **Step 1: Failing tests.**
  - restic (real binary, temp folders, follow the fixtures already in the file): `test_probe_says_an_empty_folder_holds_no_repository` (returns a string, and the folder is still empty afterwards), `test_probe_finds_an_existing_repository` (returns `None`), `test_probe_raises_on_a_wrong_password`, `test_probe_treats_an_unanswering_remote_as_out_of_reach` (drive `classify`/`_run` the way the file already simulates restic exits; repo location `rclone:nas:photos`, generic exit 1 → a string), `test_probe_raises_on_a_generic_failure_of_a_local_repository`.
  - mirror (with the fake Proton tool the file already uses): missing backup folder → reason string and no tool call; tool answers → `None`; not signed in → `MirrorSignInError`; remote folder gone → `MirrorError`; any other tool error → reason string.
- [ ] **Step 2: Run, confirm they fail** for the missing method.
- [ ] **Step 3: Implement** ports, adapters, fakes.
- [ ] **Step 4:** `just check`.
- [ ] **Step 5: Commit** `feat(backup): probe a repository and the Proton copy before using them`.

---

### Task 3: Skip, continue, catch up (the service)

**Files:**
- Modify: `B/app/backup.py`
- Test: `T/app/test_backup.py`

**Interfaces — Consumes:** `BackupRunStatus.SKIPPED`, `backup_due`, `probe_allowed` (Task 1); `BackupEngine.probe`, `RepositoryMirror.probe` (Task 2).

**Behaviour:**

1. `_backup(target)`:
   - `established = self._store.last_run(target.id, RunKind.BACKUP, succeeded_only=True) is not None`.
   - If established: `reason = self._engine.probe(repo)`; if not `None`, return `self._skipped(target, reason)`. Never call `ensure_repository` for an established target.
   - If not established: call `ensure_repository` as today, but catch `RepositoryNotFoundError` and return `self._skipped(target, str(exc))`.
   - `_skipped` returns `RunOutcome(BackupRunStatus.SKIPPED, error=<friendly>, details=reason)` where friendly is `f"{label} is not connected: plug it in and the backup starts by itself"` for `TargetKind.LOCAL` and `f"{label} cannot be reached right now: it is backed up as soon as it can be"` for `RCLONE`.
2. `mirror_now`: inside `work`, first `reason = mirror.probe(Path(target.repository), remote)`; if not `None` return `RunOutcome(BackupRunStatus.SKIPPED, error="the copy on Proton Drive waits until this computer is online and the backup disk is connected", details=reason)`.
3. `_last_attempt` ignores skipped runs: use the latest BACKUP run whose status is not `SKIPPED` (walk `self._store.list_runs(target.id)`; no store change), else `target.created_at`.
4. `run_due` for each enabled target:
   - `latest = self._store.last_run(target.id, RunKind.BACKUP)`; `waiting = latest is not None and latest.status is SKIPPED`.
   - `overdue` computed as `_status` does (extract a small `_overdue(target, now)` helper and use it in both places).
   - Skip the target unless `backup_due(schedule, last_attempt, now, window, catching_up=waiting and overdue)`.
   - If `waiting`: if not `probe_allowed(self._probed.get(("backup", target.id)), clock_now)` continue; record the probe time; if `self._engine.probe(repo)` is not `None` continue (no new row); a `BackupError` from the probe falls through to `run_now` so it is recorded as failed.
   - Otherwise `run_now`.
   - Then, for each enabled target with `mirror_path` whose latest MIRROR run is `SKIPPED`: same throttle with key `("mirror", target.id)`; when `mirror.probe(...)` returns `None`, call `mirror_now`. Exceptions from the mirror probe: call `mirror_now` so they are recorded.
   - `self._probed: dict[tuple[str, int], datetime] = {}` is set in `__init__`; it is deliberately in memory (after a restart one extra probe happens, nothing is written).
   - After the loop log one line: `log.info("backup round", extra={"results": [{"target": label, "result": status} ...]})` listing every target looked at, with `"waiting"` for one that was probed and is still absent.
5. `_record`: unchanged, except the warning log is not emitted for a skipped outcome.
6. `_status` fills `skipped_since` (latest BACKUP run's `started_at` when it is skipped) and `mirror_overdue` (`is_overdue(schedule, last_mirror_at local, target.created_at local, now)` when `mirror_path` is set, else `False`).
7. New method `protection(self) -> Protection: return protection(self.status())`.

- [ ] **Step 1: Failing tests** in `T/app/test_backup.py`, using `World`:
  - `test_an_established_backup_whose_disk_is_gone_is_skipped_and_never_created_again`: run once (succeeds), set `world.engine.absent = "no repository"`, clear `world.engine.calls`, `run_now` → status `SKIPPED`, `"ensure" not in calls`, `"backup" not in calls`, error mentions "plug it in".
  - `test_a_new_target_still_gets_its_repository_created`: first run calls `ensure`.
  - `test_a_first_backup_to_an_unplugged_disk_is_skipped_not_failed`: `world.engine.fail["ensure"] = RepositoryNotFoundError("…does not exist")` → `SKIPPED`.
  - `test_one_absent_place_does_not_stop_the_next`: two targets, mark only the first absent (extend `FakeEngine.absent` to a `dict[str, str]` keyed by repository location if needed), `run_due` at 02:31 → first skipped, second succeeded.
  - `test_while_a_place_stays_away_history_keeps_one_skipped_line`: after the skip, step the clock by 16 minutes four times calling `run_due`; `len(world.store.list_runs(target_id)) == 1` and the engine was probed, not more than once per 15 minutes.
  - `test_a_place_that_comes_back_is_backed_up_within_the_retry_time`: skipped at 02:31, present again, `run_due` at 02:50 → one succeeded run, and the copy follows when a mirror is set.
  - `test_catch_up_waits_for_the_quiet_window_unless_overdue`: window `22:00-06:00`; back at noon the same day → nothing; back at noon three days later → runs.
  - `test_a_wrong_password_is_still_a_failure`.
  - `test_the_copy_waits_when_proton_is_out_of_reach_and_catches_up`: `world.mirror.absent = "offline"` → MIRROR run `SKIPPED`, status has `mirror_error is None`; cleared and 16 minutes later `run_due` → a succeeded MIRROR run.
  - `test_protection_counts_the_disk_and_its_copy`: one target with a copy, both fresh → `protection().protected`.
- [ ] **Step 2: Run, confirm each fails for the right reason.**
- [ ] **Step 3: Implement.** Keep `run_due` readable: extract `_catch_up_backup(target, now)` and `_catch_up_copy(target)` rather than one long loop body.
- [ ] **Step 4:** the whole `T/app/test_backup.py` and `T/app/test_backup_end_to_end.py` stay green without edits to existing assertions (if one must change, stop and report why). `just check`.
- [ ] **Step 5: Commit** `feat(backup): skip a place that is not connected and catch it up when it returns`.

---

### Task 4: Health endpoint

**Files:**
- Modify: `B/api/routes/backup.py`
- Test: `T/api/test_backup_routes.py`

**Interfaces — Produces:**

```
GET /api/backups/health   (admin only, like every route of this router)
200 {"protected": bool, "places_ok": int, "places_total": int,
     "problems": [{"severity": "alert"|"warning", "message": str, "target_id": int|null}]}
```

`TargetOut` gains `skipped_since: datetime | None` and `mirror_overdue: bool`.
Declare the `/health` route before any `/{target_id}` route so it is not captured.

- [ ] **Step 1: Failing tests:** `test_health_with_no_backup_warns_that_none_is_set_up`, `test_health_is_protected_with_two_fresh_places`, `test_health_is_admin_only` (member → 403), `test_a_target_reports_since_when_it_is_skipped`. Follow the fixtures already in the file.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement** `ProblemOut`, `HealthOut.of(Protection)` and the route calling `service.protection()`.
- [ ] **Step 4:** `just check`. If the repo keeps an API contract file under `docs/contracts/`, add the route there.
- [ ] **Step 5: Commit** `feat(api): backup health for the two-places rule`.

---

### Task 5: Web — banner everywhere, one row per place

**Files:**
- Modify: `W/lib/api/types.ts`, `W/lib/api/client.ts`, `W/routes/+layout.svelte`, `W/routes/admin/+page.svelte`, `W/lib/components/admin/Backups.svelte`, the mock API under `web/mock-api/` and its spec
- Create: `W/lib/components/BackupBanner.svelte`, `W/lib/components/BackupBanner.svelte.spec.ts`
- Test: add to `web/e2e/admin.spec.ts`; screenshots via the existing `pnpm screenshots` flow

**Interfaces — Consumes:** the endpoint and fields of Task 4.

```ts
export type BackupProblem = { severity: 'alert' | 'warning'; message: string; target_id: Id | null };
export type BackupHealth = { protected: boolean; places_ok: number; places_total: number; problems: BackupProblem[] };
// BackupRun['status'] gains 'skipped'; BackupTarget gains skipped_since: string | null, mirror_overdue: boolean
// client: backupHealth: () => get<BackupHealth>('/api/backups/health')
```

**Behaviour:**

- `BackupBanner.svelte`: props `{ health: BackupHealth | null }`. Renders nothing when `health` is null or has no problems. Otherwise one line: the first problem's message, then `· and N more` when there are others, then a link `Backups` to `/admin#a-backups`. `role="alert"` when the first problem is an alert, `role="status"` otherwise. Style it with the existing tokens, in the manner of the `.banner` rule in `W/routes/admin/+page.svelte` (read `docs/DESIGN_PRINCIPLES.md`: ink and rules, no warning colours). No dismiss control.
- `+layout.svelte`: when `session.isAdmin` and not `bare`, load `api.backupHealth()` on mount and again whenever `page.url.pathname` changes; a failed load shows nothing (members and offline pages must not break). Render `<BackupBanner {health} />` as the first child of `<main>`.
- `admin/+page.svelte`: remove the old `attention` banner and its derived value.
- `Backups.svelte`:
  - Header line under the title from a new `health` prop: `Protected in {places_ok} places` when protected, else `Only {places_ok} of {places_total} places up to date`; nothing when `places_total === 0` (the existing empty text covers it).
  - `lastLine`: a skipped run reads `not connected since {formatWhen(t.skipped_since ?? run.started_at)}`.
  - The Proton copy becomes its own indented row under its target (name `Copy on Proton Drive`, the place name, then its state: `up to date {when}`, `waiting to go online`, `failed: {reason}`, `first copy after the next backup`).
  - A status dot before each place name with an accessible label: `ok`, `not connected`, `needs attention`. Shape/weight carries the state, not colour alone.
  - Recent runs: a skipped row uses the `quiet` style and the word `skipped`; a failed row uses the `attention` style.
- Mock API: add `/api/backups/health` computed from its targets and the two new target fields.

- [ ] **Step 1: Failing tests.** Component spec: nothing rendered without problems; first problem shown with `and 2 more`; `role` follows severity; link points to `/admin#a-backups`. Mock-API spec: health for zero and two targets. e2e: an admin sees the banner on `/` when the mock has one backup place, a member does not, and the admin backup section shows the "Only 1 of 1" header line.
- [ ] **Step 2: Run, confirm failure:** `cd web && pnpm test` and `pnpm e2e -g backup`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `just check`; `pnpm e2e`; take desktop and phone screenshots of the banner and the backup section with `pnpm screenshots` and look at them (banner must not cover the nav or the bottom bar on phone).
- [ ] **Step 5: Commit** `feat(ui): backup warning on every page and one row per backup place`.

---

### Task 6: Docs and guide

**Files:** `docs/FEATURES.md` (§9b: add rows for skipped places, the two-places rule and the global banner, marked done), `docs/ARCHITECTURE.md` (backup section: probe before backup, no re-init), `docs/guides/backups.md` (what "not connected" means and that plugging the disk in is enough), `CONTEXT.md` (glossary: Backup place, Skipped run, Protected).

- [ ] **Step 1:** Edit the four files; keep each addition to a few lines in the file's own voice.
- [ ] **Step 2:** `just check`.
- [ ] **Step 3: Commit** `docs(backup): skipped places, two-places rule, banner`.
