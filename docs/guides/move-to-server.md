# Move the library from the laptop to the server

The library is one folder (`PA_DATA_ROOT`). Every path in the database is relative to it, so
moving is: copy the folder, point the setting at it, start. A test copies a library to a new
place and checks every photo still opens (ARCHITECTURE §6).

## 1. Before you start

- Make sure a backup ran recently: `just backup list` (see [backups.md](backups.md)).
- Stop imports on the laptop. Leave the app running or stop it — the export takes a
  consistent database snapshot either way.
- The server needs: Ubuntu, enough disk (library size + 20 %), and either Docker or the
  same packages as the laptop ([deploy-laptop.md](deploy-laptop.md) step 1).

## 2. Export on the laptop

To an external disk:

```bash
just export-library /media/$USER/BigDisk/photo-library
```

…or straight to the server over the network (mount it first, e.g. with
`sshfs server:/srv/photo-assistant /mnt/server`) and export into it.

What it does: snapshots the database (never copies the live file), copies originals,
edit recipes, settings and thumbnails, checks every copy's hash, then re-checks every photo
at the destination. It prints a summary and the path to use. **It is resumable**: if the cable
comes out or the laptop sleeps, run the same command again and it continues. Add
`--skip-derived` to leave thumbnails out (smaller; the server rebuilds them, which takes hours).

## 3. Put it on the server and verify

```bash
sudo mkdir -p /srv/photo-assistant && sudo chown $USER: /srv/photo-assistant
rsync -a --info=progress2 /media/$USER/BigDisk/photo-library/ /srv/photo-assistant/data/
git clone <repo-url> ~/photo-assistant && cd ~/photo-assistant && just setup
PA_DATA_ROOT=/srv/photo-assistant/data just verify-library
```

`verify-library` must say "Every photo is present and intact." If it lists missing or
corrupt files, copy again (step 2 is resumable) — don't start the server on a broken copy.

## 4. Run on the server

### Option A: Docker (recommended on the server)

```bash
mkdir -p /srv/photo-assistant/secrets /srv/photo-assistant/backup
cp deploy/server.env.example deploy/server.env     # set PA_ALLOWED_HOSTS
docker compose -f deploy/compose.yml up -d --build
docker compose -f deploy/compose.yml logs -f
curl http://127.0.0.1:8420/api/health
docker compose -f deploy/compose.yml exec photo-assistant python -m photo_assistant.api.cli_ops doctor
```

> **The Docker image has not been built yet** (it was written without a Docker daemon). The
> first build on the server is its test: if a step fails, the error names the line. Base image
> tags are pinned in `deploy/Dockerfile` (`ARG …_IMAGE`); if one no longer exists, pick the
> nearest newer patch tag.

The container runs as UID 1000. If your user on the server has another id (`id -u`), build with
`docker compose build --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g)`.
The port is published on the server's 127.0.0.1 only; other devices use Tailscale.

Update: `git pull && docker compose -f deploy/compose.yml up -d --build`.

### Option B: systemd, like the laptop

Set `PA_DATA_ROOT=/srv/photo-assistant/data` in `.env`, then `just install-service` and
`sudo loginctl enable-linger $USER`.

## 5. Switch over

1. Set up remote access on the server: [remote-access.md](remote-access.md).
2. Move backup targets: on the server, add them again (`just backup add …`) with the same
   repository and password file — snapshots continue the same history (restic snapshots
   are tagged by app, not by machine path). Inside Docker, use paths under `/backup` and
   `/secrets`.
3. On the laptop: `just uninstall-service`. Keep the old `~/PhotoAssistant/data` until the
   server has run for a few weeks and a backup + restore test succeeded there; then delete it
   yourself.
4. The laptop is now just a browser: open `https://photos.<tailnet>.ts.net`.
