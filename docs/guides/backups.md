# Backups

The library is the one place everything ends up, so it gets its own backups. They use
**restic**: incremental (only new data is sent), deduplicated, encrypted, versioned.

What is backed up: originals, edit recipes, settings, the phone inbox and a consistent
snapshot of the database (taken with SQLite's backup API just before each run — the live
database file is never copied). Thumbnails and previews are skipped: they are rebuilt from the
originals. Your library is only ever read; a failed backup changes nothing in it.

Have **two** targets: an external disk at home and a second machine (the server, later a
friend's or a cloud). Each has its own schedule.

## 1. The password file (once)

restic encrypts everything with a password. Keep it **outside** the library, and keep a copy
somewhere safe (password manager, paper). Without it, the backup cannot be read — by anyone,
including you.

```bash
mkdir -p ~/.config/photo-assistant && chmod 700 ~/.config/photo-assistant
openssl rand -base64 32 > ~/.config/photo-assistant/restic-password
chmod 600 ~/.config/photo-assistant/restic-password
cat ~/.config/photo-assistant/restic-password      # copy this into your password manager now
```

## 2. Target 1: an external disk

Plug the disk in (Ubuntu mounts it at `/media/$USER/<name>`), then:

```bash
just backup add "External disk" /media/$USER/BackupDisk/photo-backup \
    --password-file ~/.config/photo-assistant/restic-password \
    --schedule "daily 02:30" --quiet-window 22:00-07:00
just backup run 1          # first run creates the repository and copies everything (slow once)
```

If the disk isn't plugged in when a backup is due, the run fails with "plug in / mount the
backup disk" — it never creates a backup on the laptop's own disk by mistake.

## 3. Target 2: the server (over SSH, via rclone)

On the laptop, describe the server to rclone once:

```bash
rclone config create server sftp host=server.tail1234.ts.net user=$USER key_file=~/.ssh/id_ed25519
rclone mkdir server:/srv/photo-backup
just backup add "Server" rclone:server:/srv/photo-backup \
    --password-file ~/.config/photo-assistant/restic-password --schedule "weekly sun 03:00"
just backup run 2
```

Any rclone remote works the same way (SMB/NAS, another SFTP machine, a cloud drive).
The rclone configuration stays in `~/.config/rclone/`, never in the library.

## 4. Schedules

| Schedule | Means |
|---|---|
| `manual` | only when you run it |
| `hourly` | every full hour |
| `daily 02:30` | every day at 02:30 |
| `weekly sun 03:00` | Sundays at 03:00 |

`--quiet-window 22:00-07:00` (optional) allows scheduled runs only in those hours; a slot
outside waits for the window. If the laptop was off, a missed backup runs once when it is back.

Scheduled runs happen inside the running app. If the app isn't running, nothing is
scheduled — run `just backup run-due` yourself (or from a systemd timer/cron).

Retention (default): keep 7 daily, 4 weekly and 12 monthly snapshots; older ones are removed
after each backup (`--keep-daily/--keep-weekly/--keep-monthly` on `add`).

## 5. Status

```bash
just backup list
```

Shows each target: ok / OVERDUE / FAILED, last success, next run, size, and the last error.
A target is **overdue** when it had no success for two intervals (e.g. two days for a daily
one). The web app shows the same as a warning banner.

## 6. Restore drill (do it once a month, and at every QA session)

Quick, automatic — restores a random sample of photos plus the database to a temporary folder
and checks every photo's hash against the database:

```bash
just backup restore-test 1
just backup check 1 --read-data 5%     # also re-reads 5 % of the stored data
```

Full restore onto a new machine (the real thing; try it once per milestone with a spare disk):

```bash
export RESTIC_PASSWORD_FILE=~/.config/photo-assistant/restic-password
restic -r /media/$USER/BackupDisk/photo-backup snapshots                 # pick one, or use latest
mkdir -p ~/PhotoAssistant/restored
restic -r /media/$USER/BackupDisk/photo-backup restore latest --target ~/PhotoAssistant/restored
cd ~/PhotoAssistant/restored && mv db-snapshot/library.db ./library.db && rmdir db-snapshot
PA_DATA_ROOT=~/PhotoAssistant/restored just verify-library --skip-derived
```

Then point `PA_DATA_ROOT` at it and start the app; thumbnails are rebuilt in the background.
Restore into a **new** folder, never over an existing library.

## Troubleshooting

| Message | Fix |
|---|---|
| `wrong password for the backup` | the password file changed; restore it from your password manager |
| `no backup repository at … plug in` | mount the disk / check the server is reachable |
| `locked by another run` | if nothing else is running: `restic -r <repo> unlock` |
| `some library files could not be read` | run `just verify-library`; check disk health |
