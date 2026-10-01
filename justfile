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

# --- operations (docs/guides/) -----------------------------------------------------------------

# Check this machine: tools, HEIC support, disk, data folder, database, backups.
doctor:
    cd backend && uv run python -m photo_assistant.api.cli_ops doctor

# Copy the whole library to DEST with a consistent DB snapshot, verified (resumable).
[positional-arguments]
export-library dest *args:
    #!/usr/bin/env bash
    set -euo pipefail
    dest="$(cd "{{invocation_directory()}}" && realpath -m -- "$1")"
    shift
    cd backend && uv run python -m photo_assistant.api.cli_ops export-library "$dest" "$@"

# Check every photo's file and hash (default: the configured library).
[positional-arguments]
verify-library *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then
        root="$(cd "{{invocation_directory()}}" && realpath -- "$1")"; shift; set -- "$root" "$@"
    fi
    cd backend && uv run python -m photo_assistant.api.cli_ops verify-library "$@"

# Backups: just backup list | add | run ID | check ID | restore-test ID (docs/guides/backups.md)
[positional-arguments]
backup *args:
    cd backend && uv run python -m photo_assistant.api.cli_ops backup "$@"

# Install and start the systemd user service (laptop). Builds the web app first.
install-service: build
    #!/usr/bin/env bash
    set -euo pipefail
    repo="$(pwd)"
    [ -f "$repo/.env" ] || { echo "create $repo/.env first (cp .env.example .env)"; exit 1; }
    [ -x "$repo/backend/.venv/bin/python" ] || { echo "run 'just setup' first"; exit 1; }
    unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$unit_dir"
    sed "s|@REPO@|$repo|g" deploy/photo-assistant.service > "$unit_dir/photo-assistant.service"
    systemctl --user daemon-reload
    systemctl --user enable --now photo-assistant.service
    systemctl --user --no-pager status photo-assistant.service | head -5 || true
    echo
    echo "Running on http://127.0.0.1:8420 — logs: journalctl --user -u photo-assistant -f"
    if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
        echo "To keep it running when you are logged out (and start at boot), run once:"
        echo "    sudo loginctl enable-linger $USER"
    fi

# Stop and remove the systemd user service. The library is not touched.
uninstall-service:
    #!/usr/bin/env bash
    set -euo pipefail
    unit="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/photo-assistant.service"
    systemctl --user disable --now photo-assistant.service 2>/dev/null || true
    rm -f "$unit"
    systemctl --user daemon-reload
    echo "Service removed. Your library and settings are untouched."
