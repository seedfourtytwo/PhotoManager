# Working in this repo (agents and humans)

Read before any change: `docs/ENGINEERING_RULES.md`, `docs/DESIGN_PRINCIPLES.md`,
the issue you are working on, and the relevant section of `docs/ARCHITECTURE.md`.

## The loop

1. Pick exactly one issue. Restate its acceptance criteria as test names before writing code.
2. Write the failing test(s). Run them. Confirm they fail for the right reason.
3. Write the minimum code to pass. Run `just check`.
4. Refactor on green. Commit with Conventional Commits.
5. Open a PR using the template; include test evidence and, for UI, desktop + phone screenshots.

## Hard stops — ask the human instead of guessing

- Anything that could write to, move or delete a **source** file or a library original.
- Schema changes not described in the issue.
- A new dependency not listed in `TECH_DECISIONS.md`.
- Anything that sends photo data or metadata off the machine.
- Weakening a test, lowering a coverage threshold, or skipping a check to get green.

## Boundaries

- Stay inside the module your issue names. Parallel agents own different areas
  (`ingest`, `ui`, `print`, `ai`); if you must touch another area, say so in the PR.
- `domain/` stays pure: no I/O, no framework imports.
- Real family photos never enter the repo, logs, screenshots or test fixtures.

## Commands

```
just setup     # install everything
just dev       # run api + web with reload
just check     # lint, layer contracts, types, all tests (what CI runs)
just fmt       # auto-fix formatting
# coming: just e2e (Playwright, desktop + phone), just qa (pre-release checklist)
```
