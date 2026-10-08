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

# Give an account a new 4-digit PIN (asks for it). For a forgotten PIN: just set-pin ck
set-pin username:
    cd backend && uv run python -m photo_assistant set-pin {{username}}

# List the folders the library imports from.
sources:
    cd backend && uv run python -m photo_assistant sources

# Examples: just models · just models --clip XLM-Roberta-Large-Vit-B-32 · just models --faces yunet_sface
# Download the local ML models into <data_root>/models (run on the laptop; needs internet).
models *args:
    cd backend && uv run python scripts/download_models.py {{args}}

# After `just models`: queue CLIP, faces and tags for every photo not analysed yet.
ml-backfill:
    cd backend && uv run python -m photo_assistant ml-backfill

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

# Quick feedback while coding: backend tests without the integration ones (no exiftool, libvips,
# restic or rclone runs). Not a substitute for `just check`.
test-fast:
    cd backend && uv run pytest -m "not integration" -q

test-web:
    cd web && pnpm test

# E2E (Playwright, desktop 1440x900 + phone 390x844) against the REAL backend: a synthetic
# library, a throw-away data root and a test-mode server on 127.0.0.1:8440. Never your library.
e2e *args:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp="$(mktemp -d)"
    server=""
    trap '[ -n "$server" ] && kill "$server" 2>/dev/null; rm -rf "$tmp"' EXIT
    echo "Synthetic library and seeded data root in $tmp …"
    (cd backend && uv run python scripts/make_mock_library.py "$tmp/src" --count 150 --size 800 >/dev/null)
    (cd backend && uv run python scripts/e2e_seed.py "$tmp/src" "$tmp/data" --scans "$tmp/scans")
    (cd web && pnpm build >/dev/null)
    web="$(cd web/build && pwd)"
    (cd backend && PA_DATA_ROOT="$tmp/data" PA_TEST_MODE=1 PA_HOST=127.0.0.1 PA_PORT=8440 \
        PA_ALLOWED_HOSTS='["127.0.0.1","localhost"]' PA_MIN_FREE_GB=0 PA_WEB_DIR="$web" \
        PA_BACKUP_ENABLED=false PA_BACKUP_KEY_DIR="$tmp/backup-keys" \
        exec uv run env HOME="$tmp" python -m photo_assistant >"$tmp/server.log" 2>&1) &
    server=$!
    for _ in $(seq 60); do curl -sf http://127.0.0.1:8440/api/health >/dev/null && break; sleep 0.5; done
    cd web && E2E_BASE_URL=http://127.0.0.1:8440 E2E_RESET_URL=http://127.0.0.1:8440/__test/reset \
        E2E_SCANS_DIR="$tmp/scans" pnpm exec playwright test {{args}}

# The same E2E suite against the in-memory mock API (no backend needed).
e2e-mock *args:
    cd web && pnpm e2e {{args}}

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
    cd backend && uv run python -m photo_assistant doctor

# Copy the whole library to DEST with a consistent DB snapshot, verified (resumable).
[positional-arguments]
export-library dest *args:
    #!/usr/bin/env bash
    set -euo pipefail
    dest="$(cd "{{invocation_directory()}}" && realpath -m -- "$1")"
    shift
    cd backend && uv run python -m photo_assistant export-library "$dest" "$@"

# Check every photo's file and hash (default: the configured library).
[positional-arguments]
verify-library *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then
        root="$(cd "{{invocation_directory()}}" && realpath -- "$1")"; shift; set -- "$root" "$@"
    fi
    cd backend && uv run python -m photo_assistant verify-library "$@"

# Backups: just backup list | add | run ID | check ID | restore-test ID (docs/guides/backups.md)
[positional-arguments]
backup *args:
    cd backend && uv run python -m photo_assistant backup "$@"

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
