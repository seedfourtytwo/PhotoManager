# Photo Assistant — one entry point for every routine task. Run `just` to list recipes.
set dotenv-load := true

default:
    @just --list

# Install backend (uv) and web (pnpm) dependencies; report missing system tools.
setup:
    cd backend && uv sync
    cd web && pnpm install
    @command -v exiftool >/dev/null || echo "note: exiftool not found (needed from M1): sudo apt install libimage-exiftool-perl"
    @command -v vips >/dev/null || echo "note: libvips not found (needed from M1): sudo apt install libvips-tools"
    @command -v pre-commit >/dev/null && pre-commit install || echo "note: install pre-commit (uv tool install pre-commit) and run 'pre-commit install'"

# Run API (:8420) and web dev server (:5173) together.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    (cd backend && uv run python -m photo_assistant) &
    (cd web && pnpm dev --open) &
    wait

# Everything CI runs, in the same order. Must pass before every push.
check: lint types test

lint:
    cd backend && uv run ruff check . && uv run ruff format --check .
    cd backend && uv run lint-imports
    cd web && pnpm lint

types:
    cd backend && uv run mypy
    cd web && pnpm check

test: test-backend test-web

test-backend:
    cd backend && uv run pytest --cov

test-web:
    cd web && pnpm test

# Auto-fix formatting and simple lint issues.
fmt:
    cd backend && uv run ruff format . && uv run ruff check --fix .
    cd web && pnpm format

# Production-style build: static web app.
build:
    cd web && pnpm build
