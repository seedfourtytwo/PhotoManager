# syntax=docker/dockerfile:1.7
#
# Photo Assistant for the home server (docs/guides/move-to-server.md).
#
# !! UNTESTED: written without a Docker daemon. Build and smoke-test it on the server first:
# !!   docker compose -f deploy/compose.yml build && docker compose -f deploy/compose.yml up
# !! then open http://127.0.0.1:8420/api/health on the server.
#
# Build from the repository root (compose does this): the context is `..` from deploy/.
# Three stages: the web app (node), the Python environment (needs a compiler for pyvips),
# and a slim runtime that only gets the results.
#
# Versions are pinned. To update: change the ARGs, rebuild, run `just doctor` in the container.

ARG NODE_IMAGE=node:22.22.2-bookworm-slim
ARG PYTHON_IMAGE=python:3.12.12-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.8.17

# --- uv binary --------------------------------------------------------------------------------
FROM ${UV_IMAGE} AS uv

# --- 1. web: the static SvelteKit build ------------------------------------------------------
FROM ${NODE_IMAGE} AS web
WORKDIR /src/web
# pnpm version comes from package.json "packageManager" (pnpm@10.28.0) via corepack.
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# --- 2. python: dependencies + the app into /opt/venv ---------------------------------------
FROM ${PYTHON_IMAGE} AS python
# pyvips only ships an sdist: compile its binding against libvips (API mode, faster).
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config libvips-dev \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src/backend
# Dependencies first (cached layer), exactly as locked; dev tools are left out.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

# --- 3. runtime ------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
# libvips42: images · exiftool: metadata · libheif-plugin-libde265: iPhone HEIC ·
# restic + rclone: backups and remote targets · tini: proper signal handling as PID 1.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libvips42 \
      libimage-exiftool-perl \
      libheif-plugin-libde265 \
      restic \
      rclone \
      ca-certificates \
      tini \
 && rm -rf /var/lib/apt/lists/*

# Non-root. UID/GID 1000 matches the first user on a typical Ubuntu server, so the bind-mounted
# library stays owned by you; override with --build-arg if yours differ (`id -u`).
# ~/.config (backup keys, rclone config) and ~/.cache (restic cache) are mount points in
# compose.yml: they must exist and belong to the app user, or Docker creates them as root.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid ${APP_GID} app \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data /home/app/.config /home/app/.cache \
 && chown app:app /data /home/app/.config /home/app/.cache \
 && chmod 700 /home/app/.config

COPY --from=python /opt/venv /opt/venv
COPY --from=web /src/web/build /app/web

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PA_DATA_ROOT=/data \
    PA_WEB_DIR=/app/web \
    PA_PORT=8420
# ------------------------------------------------------------------------------------------
# !! PA_HOST=0.0.0.0 makes the server listen on every interface *inside the container*.   !!
# !! That is only safe because:                                                           !!
# !!   1. login exists (M2) — never run an image without accounts on a reachable port;    !!
# !!   2. PA_ALLOWED_HOSTS lists the exact names you use (e.g. photos.<tailnet>.ts.net),  !!
# !!      which defeats DNS rebinding;                                                     !!
# !!   3. compose.yml publishes the port on 127.0.0.1 only, and Tailscale serve is the    !!
# !!      only way in from other devices. Never publish 8420 on 0.0.0.0 or to the internet.!!
# ------------------------------------------------------------------------------------------
ENV PA_HOST=0.0.0.0

USER app
WORKDIR /home/app
VOLUME ["/data"]
EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8420/api/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "photo_assistant"]
