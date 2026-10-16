# Working in this repo (agents and humans)

Read before any change: `docs/ENGINEERING_RULES.md`, `docs/DESIGN_PRINCIPLES.md`,
the issue you are working on, and the relevant section of `docs/ARCHITECTURE.md`.

## The loop

1. Pick exactly one issue. Restate its acceptance criteria as test names before writing code.
2. Write the failing test(s). Run them. Confirm they fail for the right reason.
3. Write the minimum code to pass. Run `just check`.
4. Refactor on green. Commit with Conventional Commits.
5. Open a PR using the template; include test evidence and, for UI, desktop + phone screenshots.
6. After pushing, `just check-report`: GitHub's CI minutes are scarce (free plan), so the
   laptop's `just check` result is what shows on the PR when CI skips a job or has none left.

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
- **Real photos never leave C's machines** (laptop, home server): don't copy, stage or upload
  them to a cloud workspace, GitHub, or any other service. Tests use the synthetic fixtures.
  Real-data checks run *on the laptop* against its own folders, and only aggregate results
  (counts, timings, error reasons) come back.

## Commands

```
just setup      # install everything
just dev        # run api + web with reload
just check      # lint, layer contracts, types, all tests (what CI runs: .github/workflows/ci.yml)
just check-report  # the same, its result shown on the pushed commit on GitHub (free; CI is not)
just test-fast  # backend tests without the ones that need external tools
just fmt        # auto-fix formatting
just e2e        # Playwright, desktop + phone, against the real backend on a synthetic library
just e2e-mock   # the same suite against the in-memory mock API
just doctor     # check this machine: tools, disk, database, backups
just            # list every recipe (run, build, import, models, backup, install-service, …)
```
