# Engineering rules

These rules apply to every contributor — C, the partner, and every AI agent. When a rule
blocks you, raise it in the PR; don't quietly break it.

## 1. Non-negotiables

1. **Originals are sacred.** No code path writes to, moves, renames or deletes a source file.
   Library originals are written once and verified by hash. A test fixture asserts source
   folders are byte-identical before and after every import test.
2. **Test first.** Red → green → refactor. The PR shows the failing test commit before the fix
   commit (or the test is clearly written against the spec, not the implementation).
3. **Main is always releasable.** `just check` green, app starts, migrations apply. CI
   (`.github/workflows/ci.yml`) runs the same checks on every pull request; the browser
   tests (`just e2e`, `just e2e-mock`) run locally.
4. **No secrets in the repo.** gitleaks runs in pre-commit and in CI.
5. **Real photos stay home.** They never go to a cloud workspace, GitHub or any other service;
   development and CI use synthetic fixtures only. Real-data dry runs (QA step 2) run on the
   laptop itself and report only counts, timings and reasons.

## 2. TDD in practice

- Start from the acceptance criterion in the issue → write it as a test (API or E2E) → it fails.
- Drop down: unit tests for the domain rule you need → make them pass → wire up.
- Refactor only on green. Refactors are separate commits.
- Bug fix = first a test reproducing the bug, then the fix.

## 3. Test pyramid and targets

| Level | Scope | Speed | Coverage target |
|---|---|---|---|
| Unit | `domain/`; `app/` mostly on the real SQLite repository in memory, with small fakes for outside tools | whole suite < 10 s | one floor for the whole package, all levels together: 90 % (`fail_under` in `pyproject.toml`, branch coverage on) |
| Property | date fallback, dedup, layout fitting, crop math | seconds | key invariants listed in code |
| Contract | an adapter satisfies its port (same checks run against fake + real) | < 1 min | target: every port that has a fake. Today: the backup store only (`tests/adapters/test_backup_store.py`) |
| Integration | real ExifTool, libvips, SQLite, Typst on the fixture set | < 3 min | every adapter |
| API | FastAPI routes through httpx | < 1 min | every route, incl. auth & private items |
| E2E | Playwright: import → browse → album → PDF, desktop + phone viewport | < 5 min | the 6 golden journeys |
| Visual | Playwright screenshots of key views; PDF page renders compared to goldens | — | layouts & themes |
| Accessibility | axe-core in E2E | — | zero serious/critical violations |

Coverage is a floor, not a goal. A test that asserts nothing useful is worse than none.

### Fixture library
`tests/fixtures/photos/` — 18 small files, all drawn by `scripts/make_fixtures.py` (nothing
third-party), covering: HEIC with its Live Photo video, PNG screenshot with the date only in
its name, no EXIF, a placeholder EXIF date, GPS / no GPS, rotated EXIF, an iPhone edited copy,
exact duplicate under two names, truncated file, text named `.jpg`, 0-byte file, emoji file
name, a 1×1 image, and files that must be skipped or ignored (PDF, video, `.AAE`,
`.DS_Store`). What importing them must give is in `tests/fixtures/expected.py`. Not in the
set: RAW-with-preview, wrong timezone, burst, near-duplicate.
Never commit real family photos.

## 4. Clean code

- **Small, named things.** Functions do one thing; ~20 lines is a smell trigger, not a law.
  Names say intent (`pick_capture_time`, not `process_date`).
- **Pure core, thin shell.** Decisions live in `domain/` as pure functions; I/O at the edges.
- **Types everywhere.** mypy strict on `domain/` and `app/`; TypeScript strict; no `Any`
  without a comment explaining why.
- **Explicit errors.** Never swallow exceptions; user-facing messages say what happened and
  what to do. An error a person can cause or must read is a named subclass of a family in
  `domain/errors.py` (`NotFoundError`, `ForbiddenError`, `InvalidError`, `ConflictError`,
  `UnavailableError`; plain `DomainError` is a 400), raised where the rule lives
  (`SourceUnavailableError`, `InvalidScheduleError`). The family is the HTTP status: one
  handler in `api/main.py` answers them all, so routes do not write
  `except …: raise HTTPException`, and never catch a bare `ValueError` of our own.
  The job worker does not retry a `DomainError`, so an error that may pass by waiting (network,
  a locked repository, a slow tool) stays outside the hierarchy. Every class outside it is
  listed with its reason in `tests/unit/test_error_hierarchy.py`; that test fails for a new
  exception class that is neither. The routes that still translate by hand are listed in
  `ARCHITECTURE.md` §7.
- **No speculative generality.** Build the second implementation when the second case exists
  (exception: the AI port, which exists by design with a Null implementation).
- **Comments explain *why*.** The code explains what.
- **Dependencies are decisions.** A new dependency needs a line in `TECH_DECISIONS.md`.
- **Config** via environment variables (`PA_*`, also read from `.env`) validated by
  pydantic-settings; there is no settings file. No magic constants in code.

## 5. Git & PR workflow

- Branch per issue: `feat/12-justified-grid`, `fix/31-heic-rotation`.
- Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`).
- PRs small: aim < 400 changed lines excluding fixtures/snapshots.
- PR template: linked issue · what & why · screenshots (desktop + phone) for UI · test evidence ·
  checklist below.
- Squash-merge to `main`.

## 6. Definition of Done (every PR)

- [ ] Acceptance criteria of the issue are covered by tests that ran red first
- [ ] `just check` passes locally (lint, format, types, unit, integration)
- [ ] E2E for touched journeys passes on desktop + phone viewport
- [ ] No new axe violations; UI follows `DESIGN_PRINCIPLES.md` (reviewer ticks the checklist there)
- [ ] Originals-untouched test still green
- [ ] Docs updated (FEATURES status, ARCHITECTURE if structure changed, TECH_DECISIONS if a dep was added)
- [ ] No TODO without an issue number

## 7. QA session (before each milestone is called done)

A deliberate pass, not "CI is green":

1. **Clean-machine run:** fresh clone → `just setup` → `just dev` on the laptop. Note every friction.
2. **Real-data dry run (on the laptop, never uploaded):** import ~1,000 real photos there. Compare
   counts: files seen = imported + duplicates + skipped + failed. Explain every failure.
3. **Exploratory testing** (45 min, timeboxed) against the milestone's charter; log bugs as issues.
4. **Phone check:** open over LAN on the iPhone; install PWA; scroll, loupe, filter, album.
5. **Performance check** against the budget table in `ARCHITECTURE.md`; record numbers in the release notes.
6. **Self-review / clean-up:** dead code, stray logs, skipped tests, TODOs, dependency audit
   (`uv pip audit`/`pnpm audit`).
7. **Independent review:** a reviewer (human or a fresh agent that did not write the code)
   reads the diff for the milestone against these rules.
8. Only then: tag the release.
