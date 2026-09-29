# Engineering rules

These rules apply to every contributor — C, the partner, and every AI agent. When a rule
blocks you, raise it in the PR; don't quietly break it.

## 1. Non-negotiables

1. **Originals are sacred.** No code path writes to, moves, renames or deletes a source file.
   Library originals are written once and verified by hash. A test fixture asserts source
   folders are byte-identical before and after every import test.
2. **Test first.** Red → green → refactor. The PR shows the failing test commit before the fix
   commit (or the test is clearly written against the spec, not the implementation).
3. **Main is always releasable.** CI green, app starts, migrations apply.
4. **No secrets in the repo.** gitleaks runs in pre-commit and CI.

## 2. TDD in practice

- Start from the acceptance criterion in the issue → write it as a test (API or E2E) → it fails.
- Drop down: unit tests for the domain rule you need → make them pass → wire up.
- Refactor only on green. Refactors are separate commits.
- Bug fix = first a test reproducing the bug, then the fix.

## 3. Test pyramid and targets

| Level | Scope | Speed | Coverage target |
|---|---|---|---|
| Unit | `domain/`, `app/` with fakes | whole suite < 10 s | ≥ 95 % lines, ≥ 90 % branches |
| Property | date fallback, dedup, layout fitting, crop math | seconds | key invariants listed in code |
| Contract | each adapter satisfies its port (same test suite run against fake + real) | < 1 min | every port |
| Integration | real ExifTool, libvips, SQLite, Typst on the fixture set | < 3 min | every adapter |
| API | FastAPI routes through httpx | < 1 min | every route, incl. auth & private items |
| E2E | Playwright: import → browse → album → PDF, desktop + phone viewport | < 5 min | the 6 golden journeys |
| Visual | Playwright screenshots of key views; PDF page renders compared to goldens | — | layouts & themes |
| Accessibility | axe-core in E2E | — | zero serious/critical violations |

Coverage is a floor, not a goal. A test that asserts nothing useful is worse than none.

### Fixture library
`tests/fixtures/photos/` — ~40 small, **self-made or CC0** images covering: HEIC, RAW-with-preview,
PNG screenshot, no EXIF, wrong timezone, GPS / no GPS, rotated EXIF, Live Photo pair, burst,
exact duplicate under two names, near-duplicate, corrupt file, emoji file name, 0-byte file.
Never commit real family photos.

## 4. Clean code

- **Small, named things.** Functions do one thing; ~20 lines is a smell trigger, not a law.
  Names say intent (`pick_capture_time`, not `process_date`).
- **Pure core, thin shell.** Decisions live in `domain/` as pure functions; I/O at the edges.
- **Types everywhere.** mypy strict on `domain/` and `app/`; TypeScript strict; no `Any`
  without a comment explaining why.
- **Explicit errors.** Domain errors are typed (`UnsupportedFormat`, `SourceUnavailable`);
  never swallow exceptions; user-facing messages say what happened and what to do.
- **No speculative generality.** Build the second implementation when the second case exists
  (exception: the AI port, which exists by design with a Null implementation).
- **Comments explain *why*.** The code explains what.
- **Dependencies are decisions.** A new dependency needs a line in `TECH_DECISIONS.md`.
- **Config** via env/`settings.toml` validated by pydantic-settings; no magic constants in code.

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
2. **Real-data dry run:** import a copy of ~1,000 real photos from the laptop test set. Compare
   counts: files seen = imported + duplicates + skipped + failed. Explain every failure.
3. **Exploratory testing** (45 min, timeboxed) against the milestone's charter; log bugs as issues.
4. **Phone check:** open over LAN on the iPhone; install PWA; scroll, loupe, filter, album.
5. **Performance check** against the budget table in `ARCHITECTURE.md`; record numbers in the release notes.
6. **Self-review / clean-up:** dead code, stray logs, skipped tests, TODOs, dependency audit
   (`uv pip audit`/`pnpm audit`).
7. **Independent review:** a reviewer (human or a fresh agent that did not write the code)
   reads the diff for the milestone against these rules.
8. Only then: tag the release.
