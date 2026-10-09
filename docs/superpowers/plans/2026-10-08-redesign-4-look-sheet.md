# Redesign 4 of 4: Look sheet (per-account look) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each account carries a look (a theme, a mode, a few dials and switches) that the server validates and stores. The account itself chooses only its mode, in Settings; an admin sets the whole look of any account from Admin → People, trying it on their own screen before saving it.

**Architecture:** The allowed values live once in `domain/look.py` (pure, standard library only): a strict parser for what an admin sends and a lenient reader for what is stored. The sheet is JSON text in a nullable `look` column on `user` (null = defaults). `Accounts` gains three small use cases; one new router serves four routes. On the web, `lib/look/` mirrors the rules (`sheet.ts`, pure), turns a sheet into root attributes and CSS variables (`apply.ts`) and holds the account's sheet and a trial sheet (`look.svelte.ts`). Nothing in `lib/look/` imports the rest of the app; `app.svelte.ts` is the only place that joins it to the API. A small inline script in `app.html` applies the cached sheet before first paint, and a test keeps it equal to `apply.ts`.

**Tech Stack:** Python 3.12, FastAPI, SQLite migrations, pytest, mypy strict, import-linter · SvelteKit 2 (static), Svelte 5 runes, TypeScript strict, Vitest 4 (node project for `*.spec.ts`, browser project for `*.svelte.spec.ts`), Playwright e2e against the mock API and the real backend, pnpm.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` §5, §7 step 4, §8. Decision record: `docs/adr/0001-look-is-a-validated-sheet-not-css.md`. Issue: seedfourtytwo/PhotoManager#11. Terms: `CONTEXT.md`.

## Global Constraints

- One schema change, approved by C on 2026-10-08: a nullable `look` column on `user`. Nothing else. The migration takes the next free number on `origin/main` (0027 when this was written); check again before pushing.
- No new dependency, backend or web.
- `domain/look.py` imports the standard library only; `web/src/lib/look/` imports nothing outside itself.
- A look is values, never CSS: no colour, selector or free text is accepted or stored.
- Only tokens in components: no raw colours, sizes or spacings outside `tokens.css`, `themes.css`, `fonts.css`.
- Sheet field names are the spec's (`accentHue`, `photoGap`, …), in the API and in storage.
- Routes do not change name; `/admin` keeps the label `Admin` (the rename to System belongs to issue 10).
- Another session builds step 3 on `feat/11-photo-view` (`Loupe`, `PhotoGrid`, `Timeline`, `SelectionBar`, `SelectionActions` and the loupe/grid/actions e2e tests). Stay out of those files; the one exception is named in Task 8.
- E2E tests may be edited only where this plan names them; no assertion is weakened.
- Web unit tests run with `PA_API=http://127.0.0.1:9`; nothing may reach port 8420. Real photos never enter the repo, screenshots or fixtures.
- Branch `feat/11-look-sheet` from `origin/main`. Conventional Commits; each message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never `git stash`.

## Decisions the spec leaves open

| Question | Decision | Why |
|---|---|---|
| A number of the wrong kind (`"big"`), an unknown choice (`"neon"`) | Rejected, like an unknown field | Only numbers can be clamped; guessing a choice would hide a mistake |
| `collectionsRows: []` | Rejected | An empty Collections page leaves people and albums unreachable; ADR: a look cannot make the app unusable |
| Dials are whole numbers? | Hue, corners and gap are rounded to whole numbers, text scale to two decimals | The stored sheet is the same whoever wrote it |
| Who may set their mode | Every signed-in account, guests included | It is how their own screen looks, not a change to the library; guests could pick it before |
| `showToday`, `startPage` | Validated, stored and returned; not in the form and without effect | There is no Today page yet (spec §4.1, §9) |
| `thumbSize` and the existing "Photo size in the grid" setting | The look gives the size; a choice made on this device in Settings still wins | Removing a control people use is C's call, not this plan's |
| `corners` | Sets `--r-1`; `--r-2` follows at 5/3 (12 → 20, as in Safelight) | One dial, both radii, 0 stays square |
| `pa.theme` | Read once as the mode (also by the first-paint script), sent to the server after sign-in, then removed | Spec §5 |
| Reset | `PUT` with `{}` stores the defaults | "Reset look always works" without a fifth route |

## File Structure

| File | Responsibility |
|---|---|
| `backend/src/photo_assistant/domain/look.py` (new) | The sheet: fields, bounds, strict `parse_look`, lenient `read_look`, `look_sheet`, `dump_look`. |
| `backend/src/photo_assistant/adapters/migrations/0027_account_look.sql` (new) | `ALTER TABLE user ADD COLUMN look TEXT`. |
| `backend/src/photo_assistant/ports/accounts.py`, `adapters/sqlite_accounts.py` | `stored_look`, `store_look` on the account store. |
| `backend/src/photo_assistant/app/accounts.py` | `look_of`, `choose_mode`, `set_look`; `InvalidLookError` (422). |
| `backend/src/photo_assistant/api/routes/look.py` (new), `api/schemas.py`, `api/main.py` | The four routes. |
| `docs/contracts/api-v1.md`, `docs/ARCHITECTURE.md` | Contract v1.5; the column. |
| `web/src/lib/look/sheet.ts` (new) | Types, defaults, bounds, `parseLook` (strict), `readLook` (lenient). |
| `web/src/lib/look/apply.ts` (new) | `rootLook(sheet)` → attributes and variables; `applyLook`. |
| `web/src/lib/look/cache.ts` (new) | The cached sheet and the old `pa.theme` setting in `localStorage`. |
| `web/src/lib/look/look.svelte.ts` (new) | `look`: the account's sheet, the trial sheet, what the screen shows. |
| `web/src/app.html` | The first-paint script. |
| `web/src/lib/api/types.ts`, `client.ts`, `web/mock-api/app.ts`, `data.ts` | The API on the web side and in the mock. |
| `web/src/lib/app.svelte.ts`, `routes/+layout.svelte`, `routes/settings/+page.svelte` | Loading the look, the mode switch. |
| `web/src/lib/components/admin/LookForm.svelte` (new), `Users.svelte` | The per-account form. |
| `web/src/lib/components/LookTrial.svelte` (new) | The "Trying a look" line with Stop trying. |
| `web/src/routes/collections/+page.svelte`, `lib/components/Nav.svelte`, `lib/tokens.css` | Switches and dials that need more than a variable. |
| `web/e2e/look.spec.ts` (new) | The journeys, desktop and phone, mock and real backend. |

---

### Task 1: The sheet's rules (backend, pure)

**Files:**
- Create: `backend/src/photo_assistant/domain/look.py`, `backend/tests/unit/test_look.py`
- Modify: `backend/tests/unit/test_error_hierarchy.py`

**Interfaces:**
- Produces: `Theme`, `Mode`, `ThumbSize`, `StartPage`, `CollectionsRow` (`StrEnum`); `Look` (frozen dataclass, defaults = the spec's table); `DEFAULT_LOOK`; `LookError(ValueError)`; `parse_look(raw: object) -> Look`; `read_look(stored: str | None) -> Look`; `look_sheet(look) -> dict[str, object]`; `dump_look(look) -> str`.

- [ ] **Step 1: Write the failing tests** — acceptance lines as test names:
  - `test_an_empty_sheet_is_the_defaults`
  - `test_the_defaults_are_the_ones_in_the_spec`
  - `test_an_unknown_field_is_rejected_by_name`
  - `test_a_number_outside_its_range_is_clamped` (each dial, both ends)
  - `test_a_dial_left_to_the_theme_stays_null`
  - `test_a_value_of_the_wrong_kind_is_rejected` (text for a number, a number for a switch, `true` for a number, NaN, infinity)
  - `test_an_unknown_choice_is_rejected` (theme, mode, thumb size, start page)
  - `test_collections_rows_keep_their_order_and_refuse_repeats_strangers_and_none`
  - `test_hiding_today_starts_on_the_library`
  - `test_a_sheet_that_is_not_an_object_is_rejected`
  - `test_a_stored_sheet_reads_back_as_it_was_written`
  - `test_nothing_stored_reads_as_the_defaults`
  - `test_a_broken_stored_sheet_reads_as_the_defaults` (not JSON, a list, an unknown field, a wrong kind)
- [ ] **Step 2: Run** — `cd backend && uv run pytest tests/unit/test_look.py -q`. Expected: FAIL, no module `photo_assistant.domain.look`.
- [ ] **Step 3: Implement** `domain/look.py`; list `domain.look.LookError` in `test_error_hierarchy.py` (a signal: `Accounts` raises `InvalidLookError`).
- [ ] **Step 4: Run** — the same command, then `uv run lint-imports && uv run mypy`. Expected: PASS.
- [ ] **Step 5: Commit** — `feat(look): the look sheet's rules, pure (unknown fields rejected, numbers clamped)`.

### Task 2: The column

**Files:**
- Create: `backend/src/photo_assistant/adapters/migrations/0027_account_look.sql`
- Modify: `ports/accounts.py`, `adapters/sqlite_accounts.py`, `backend/tests/adapters/test_migrations.py`, `backend/tests/app/test_accounts.py` (its fake store, if any)

**Interfaces:**
- Produces: `AccountStore.stored_look(user_id) -> str | None`, `AccountStore.store_look(user_id, look: str) -> None`.

- [ ] **Step 1: Failing test** — `test_accounts_from_before_0027_come_through_with_no_look` in `test_migrations.py`: a library at the version before, two accounts, upgrade, `look` is null for both, `stored_look` answers `None`, a stored sheet reads back, one pre-migration copy was taken.
- [ ] **Step 2: Run** — FAIL: no column `look`.
- [ ] **Step 3: Implement** the migration and the two store methods.
- [ ] **Step 4: Run** `uv run pytest tests/adapters/test_migrations.py -q`. PASS.
- [ ] **Step 5: Commit** — `feat(look): a nullable look column on accounts (migration 0027)`.

### Task 3: Use cases and routes

**Files:**
- Create: `backend/src/photo_assistant/api/routes/look.py`, `backend/tests/api/test_look_api.py`
- Modify: `app/accounts.py`, `api/schemas.py`, `api/main.py`, `backend/tests/app/test_accounts.py`, `docs/contracts/api-v1.md`, `docs/ARCHITECTURE.md`

**Interfaces:**
- Produces: `Accounts.look_of(user_id) -> Look`, `Accounts.choose_mode(user, mode) -> Look`, `Accounts.set_look(user_id, raw) -> Look` (`UserNotFoundError`, `InvalidLookError`).
- Routes: `GET /api/me/look` → sheet · `PUT /api/me/look` `{mode}` → sheet · `GET`/`PUT /api/admin/accounts/{user_id}/look` → sheet.

- [ ] **Step 1: Failing API tests, per role:**
  - `test_a_new_account_has_the_default_look`
  - `test_a_member_changes_their_mode_and_nothing_else_moves`
  - `test_a_guest_may_choose_their_mode_too`
  - `test_a_member_cannot_send_any_other_field` (422; the look is unchanged)
  - `test_a_member_cannot_send_an_unknown_mode` (422)
  - `test_a_member_and_a_guest_cannot_read_or_set_another_accounts_look` (403)
  - `test_nobody_signed_in_gets_no_look` (401)
  - `test_an_admin_sets_any_accounts_look_and_that_account_gets_it`
  - `test_an_admin_sets_their_own_look`
  - `test_an_unknown_field_is_refused_and_nothing_is_stored` (422, sentence names the field)
  - `test_numbers_are_clamped_on_the_way_in`
  - `test_an_empty_sheet_resets_the_look`
  - `test_a_broken_stored_sheet_answers_the_defaults` (text written straight into the column)
  - `test_the_look_of_an_unknown_account_is_not_found` (404)
  - `test_a_sheet_that_is_not_an_object_is_refused` (422)
- [ ] **Step 2: Run** — FAIL: 404 for every route.
- [ ] **Step 3: Implement.** Document the routes in `api-v1.md` (the contract test finds them), the column in `ARCHITECTURE.md` §3.
- [ ] **Step 4: Run** — `just check` backend half: `uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run mypy && uv run pytest --cov`.
- [ ] **Step 5: Commit** — `feat(look): API — an account chooses its mode, an admin sets any account's look`.

### Task 4: The sheet on the web (pure)

**Files:**
- Create: `web/src/lib/look/sheet.ts`, `sheet.spec.ts`, `apply.ts`, `apply.spec.ts`, `cache.ts`, `cache.spec.ts`

**Interfaces:**
- Produces: `type Look`, `Mode`, `Theme`, `ThumbSize`, `CollectionsRow`; `DEFAULT_LOOK`; `LOOK_RANGES`; `parseLook(raw: unknown): Look` (throws `LookError`); `readLook(raw: unknown): Look`; `rootLook(look): { attributes: Record<string, string | null>; variables: Record<string, string | null> }`; `applyLook(look, root)`; `cachedLook(storage)`, `cacheLook(storage, look)`, `oldMode(storage)`, `forgetOldMode(storage)`.

- [ ] **Step 1: Failing tests** — the same cases as Task 1 for `parseLook` / `readLook` (one table of sheets shared in spirit with the backend's), plus:
  - `the default look sets the dark mode and no variable`
  - `each dial becomes its variable; a dial left to the theme removes it`
  - `the Album theme is an attribute, Safelight is its absence`
  - `following the device removes the mode attribute`
  - `corners move both radii and zero is square`
  - `the cached sheet comes back; a broken one is the defaults`
  - `the old pa.theme setting is the mode until it is forgotten`
- [ ] **Step 2: Run** — `cd web && PA_API=http://127.0.0.1:9 pnpm test src/lib/look`. FAIL: cannot resolve.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests, `pnpm check && pnpm lint`. PASS.
- [ ] **Step 5: Commit** — `feat(look): the sheet on the web — the same rules, and what it sets on the page`.

### Task 5: First paint, and the look in the app

**Files:**
- Create: `web/src/lib/look/look.svelte.ts`, `look.svelte.spec.ts`, `web/src/lib/look/boot.spec.ts`
- Modify: `web/src/app.html`, `web/src/lib/tokens.css`, `web/src/lib/api/types.ts`, `client.ts`, `web/mock-api/app.ts`, `data.ts`, `app.spec.ts`, `web/src/lib/app.svelte.ts`, `routes/+layout.svelte`, `routes/settings/+page.svelte`

**Interfaces:**
- Produces: `look.saved`, `look.trial`, `look.shown`, `look.receive(raw)`, `look.try(sheet, who)`, `look.stopTrying()`; `api.myLook()`, `api.setMyMode(mode)`, `api.accountLook(id)`, `api.setAccountLook(id, sheet)`; `loadLook()` and `chooseMode(mode)` in `app.svelte.ts`. `settings.theme`, `setTheme`, `applyTheme` and the `Theme` type are removed.

- [ ] **Step 1: Failing tests**
  - `boot.spec.ts`: `the first-paint script sets what applyLook sets` for a table of cached sheets (none, defaults, every dial, Album light, broken JSON, an old `pa.theme`), by running the script taken from `app.html` against a stand-in root and comparing with `rootLook`.
  - `look.svelte.spec.ts`: `a received sheet is shown, cached and set on the page`; `a trial is shown without being cached and ends on Stop trying`; `a sheet received while trying waits behind the trial`; `a broken sheet from the server shows the defaults`.
  - `mock-api/app.spec.ts`: `serves the look: mode for anyone, the whole sheet for an admin`.
- [ ] **Step 2: Run.** FAIL.
- [ ] **Step 3: Implement.** `loadLook()` runs after the session is known and when the tab returns to the foreground; with an old `pa.theme` it sends that mode instead of asking, then forgets the key. Settings: the "Theme" choice becomes "Mode" (Dark · Light · Like the device), saved on the account.
- [ ] **Step 4: Run** `pnpm test`, `pnpm check`, `pnpm lint`. PASS.
- [ ] **Step 5: Commit** — `feat(look): the account's look loads with the session; mode is chosen in Settings`.

### Task 6: The form in Admin → People

**Files:**
- Create: `web/src/lib/components/admin/LookForm.svelte`, `look-form.svelte.spec.ts`, `web/src/lib/components/LookTrial.svelte`
- Modify: `web/src/lib/components/admin/Users.svelte`, `routes/+layout.svelte`

- [ ] **Step 1: Failing component tests**
  - `the form opens on the account's stored look`
  - `Try on my screen shows the sheet here and saves nothing`
  - `Stop trying puts my own look back`
  - `Save for … sends the whole sheet for that account and ends the trial`
  - `Reset look puts every field back to its default (saved only by Save)`
  - `a dial left to the theme sends null`
  - `a refused save says why and keeps the form open`
  - `reopening the form while trying picks the trial up`
- [ ] **Step 2: Run.** FAIL.
- [ ] **Step 3: Implement.** A "Look" button per row opens the form in the existing `Dialog`. `LookTrial` is one line at the top of every page while a trial runs: "Trying a look for Donna." and Stop trying.
- [ ] **Step 4: Run.** PASS.
- [ ] **Step 5: Commit** — `feat(ui): an admin sets an account's look — try on my screen, then save for them`.

### Task 7: Switches

**Files:**
- Modify: `web/src/lib/nav.ts`, `nav.spec.ts`, `web/src/routes/collections/+page.svelte`, `web/src/lib/components/Nav.svelte`

- [ ] **Step 1: Failing tests** — `nav.spec.ts`: `collection rows come in the look's order and only those it names`; a component test for the dock: `without dock labels the words stay for screen readers`.
- [ ] **Step 2–4:** implement, run.
- [ ] **Step 5: Commit** — `feat(ui): the look's switches — Collections rows and dock labels`.

### Task 8: Dials that reach the grid

**Files:**
- Modify: `web/src/lib/app.svelte.ts`, `app.svelte.spec.ts`, `web/src/lib/components/JustifiedGrid.svelte`, `routes/trash/+page.svelte`, `routes/map/+page.svelte`, `routes/albums/[id]/+page.svelte`, and **two lines of `web/src/lib/components/Timeline.svelte`** (the gap between photos is a constant there; step 3 owns the file, so only the constant and its one use change).

- [ ] **Step 1: Failing tests** — `the look's thumb size is the grid size until one is chosen on this device`; `the look's photo gap is the grid gap; left to the theme it is 3`.
- [ ] **Step 2–4:** `settings.density` falls back to the look; `settings.gap` replaces the literal `3`.
- [ ] **Step 5: Commit** — `feat(ui): photo size and gap follow the account's look`.

### Task 9: Journeys, documents, proof

**Files:**
- Create: `web/e2e/look.spec.ts`
- Modify: `docs/DESIGN_PRINCIPLES.md`, `docs/FEATURES.md`, `docs/wiring/web.md` if it names `pa.theme`, `web/e2e/screenshots.spec.ts` (new shots only), `docs/screenshots/integrated/**`

- [ ] **Step 1: E2E, desktop + phone, mock and real backend**
  - `a member chooses light in Settings and it is still light after a reload, before the app has loaded`
  - `an admin tries a look for Partner on their own screen, stops, then saves it; Partner gets it`
  - `the look form is accessible`
  - `a look set by the admin survives signing out and in`
- [ ] **Step 2: Everything** — `just check`, `just e2e-mock`, `just e2e`. Record the totals.
- [ ] **Step 3: Screenshots** — `cd web && pnpm screenshots && THEME=light pnpm screenshots`; new: `22-look-form`, `23-look-trial`.
- [ ] **Step 4: Migration number** — `git fetch origin`; the highest number in `adapters/migrations` on `origin/main` plus one is ours. Renumber (file, header comment, test name, docs) if it moved.
- [ ] **Step 5: Commit, push, PR** — `docs: the look sheet in the design principles and features; fresh screenshots`. Open the PR with the template; do not merge.
