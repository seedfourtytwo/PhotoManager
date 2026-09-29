# Photo Assistant

A private, local-first photo library for the family, with accounts and per-folder access. It collects every photo we own — from as
many local and remote folders as we point it at, plus our phones — into one de-duplicated, backed-up library, organises it
automatically, lets us browse it in calm, uncluttered views, download any selection in the
format and size we need, make simple non-destructive edits, and turn selections into albums and
print-ready photo books. AI (a local LLM) is optional and
plugs in through one well-defined socket.

> Status: **M0 (foundations)**: repo skeleton, CI and rules in place; features start in M1. Start with [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Principles in one breath

- **Originals are sacred.** The app never edits, moves or deletes a source file. Ever.
- **Local first.** Runs on the laptop today, the home server tomorrow, no cloud required.
- **Works without AI.** Every feature has a manual path; AI only makes it faster.
- **Test first.** No production code without a failing test that asked for it.
- **Quiet UI.** Tufte-inspired: the photos are the data, everything else is ink to minimise.

## Documents

| Doc | What it answers |
|---|---|
| [`docs/FEATURES.md`](docs/FEATURES.md) | What the product does, prioritised by milestone |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How it is built: modules, data model, flows |
| [`docs/TECH_DECISIONS.md`](docs/TECH_DECISIONS.md) | Which tech, why, and what we rejected |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Milestones, acceptance criteria, issue breakdown |
| [`docs/ENGINEERING_RULES.md`](docs/ENGINEERING_RULES.md) | Clean code, TDD, testing, QA, Definition of Done |
| [`docs/DESIGN_PRINCIPLES.md`](docs/DESIGN_PRINCIPLES.md) | Tufte-compliant UI rules and design tokens |
| [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) | Decisions still waiting on C |
| [`AGENTS.md`](AGENTS.md) | How AI agents (and humans) work in this repo |

## Quick start

Needs: `uv`, Node 22 + `pnpm`, `just`. From M1 also `exiftool` and `libvips`.

```bash
git clone git@github.com:<you>/photo-assistant.git && cd photo-assistant
cp .env.example .env    # set PA_DATA_ROOT if you want the library somewhere else
just setup              # installs backend + web deps, reports missing system tools
just dev                # API on :8420, web on :5173
just check              # lint, layer contracts, types, all tests: what CI runs
```

Coming in M1: `just import <folder>`. Coming later: `just e2e`, `just qa`.

## Stack (short)

Python 3.12 · FastAPI · SQLite + sqlite-vec · libvips · ExifTool · ONNX Runtime (CLIP, faces) ·
SvelteKit + TypeScript (PWA, desktop + mobile) · Typst for print PDFs · rclone for cloud sources ·
Ollama adapter for the optional local LLM.
