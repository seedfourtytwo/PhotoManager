# Photo Assistant — one entry point for every routine task. Run `just` to list recipes.
set dotenv-load := true

default:
    @just --list

# Install backend (uv) and web (pnpm) dependencies; report missing system tools.
setup:
    cd backend && uv sync
    cd web && pnpm install
    @command -v exiftool >/dev/null || echo "missing: exiftool — sudo apt install libimage-exiftool-perl"
    @command -v vips >/dev/null || echo "missing: libvips — sudo apt install libvips42 libvips-tools"
    @ls /usr/lib/*/libheif/plugins/*de265* >/dev/null 2>&1 || echo "missing: iPhone HEIC support — sudo apt install libheif-plugin-libde265"
    @command -v pre-commit >/dev/null && pre-commit install || echo "note: install pre-commit (uv tool install pre-commit) and run 'pre-commit install'"

# Run API (:8420) and web dev server (:5173) together.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    (cd backend && uv run python -m photo_assistant) &
    (cd web && pnpm dev --open) &
    wait

# Import a folder into the library (read-only on the folder). Example: just import ~/Pictures
[positional-arguments]
import folder *args:
    #!/usr/bin/env bash
    set -euo pipefail
    folder="$(cd "{{invocation_directory()}}" && realpath -- "$1")"
    shift
    cd backend && uv run python -m photo_assistant import "$folder" "$@"

# List the folders the library imports from.
sources:
    cd backend && uv run python -m photo_assistant sources

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

# Build the web app and serve everything from one process on http://127.0.0.1:8420
run: build
    cd backend && PA_WEB_DIR="$(cd ../web/build && pwd)" uv run python -m photo_assistant
