# Run Photo Assistant on the laptop (Ubuntu)

About 15 minutes. The library lives in `~/PhotoAssistant/data`; your photo folders are only
ever read.

## 1. Install the system tools (once)

```bash
sudo apt install git libimage-exiftool-perl libvips42 libheif-plugin-libde265 restic rclone
curl -LsSf https://astral.sh/uv/install.sh | sh          # Python package manager
sudo apt install nodejs npm && sudo npm install -g corepack && corepack enable   # pnpm for the web app
uv tool install rust-just                                 # the `just` command (or: sudo apt install just)
```

`restic` and `rclone` are only needed for backups; everything else is required.

## 2. Get the code and set it up

```bash
git clone git@github.com:seedfourtytwo/PhotoManager.git ~/photo-assistant && cd ~/photo-assistant
cp .env.example .env            # PA_DATA_ROOT is the only setting you must check
just setup                      # installs everything, says what is missing
just doctor                     # checklist: every line should be ok (or -- for optional)
```

If `just doctor` shows `FAIL`, it prints the command that fixes it.

## 3. Import photos

```bash
just import ~/Pictures          # read-only on ~/Pictures; copies into the library
just import /media/$USER/OldDisk/Photos --label "Old disk"
```

Or in the web app, without typing a path: **Admin → Folders → Add folder**, click your way
to the folder (it starts in your home folder; plugged-in disks are listed on top), then
**Add and import**. The folder is only ever read.

Each import ends with a summary: seen = imported + duplicates + skipped + failed, and
every skip or failure says why. Running it again only picks up new files.

## 4. Run it

Pick one:

- **By hand:** `just run` → open <http://127.0.0.1:8420>. Stops when you close the terminal.
- **As a service (recommended):** `just install-service`. It starts now and whenever you log
  in. To keep it running when you are logged out and start it at boot, run once:
  `sudo loginctl enable-linger $USER`.

Service commands:

| What | Command |
|---|---|
| Status | `systemctl --user status photo-assistant` |
| Live logs | `journalctl --user -u photo-assistant -f` |
| Restart | `systemctl --user restart photo-assistant` |
| Remove | `just uninstall-service` (the library is not touched) |

App logs are also in `~/PhotoAssistant/data/logs/`.

The service is niced, has a 2 GB memory cap (it restarts instead of freezing the laptop),
and listens on 127.0.0.1 only.

## 4b. First visit: create the admin account

Open <http://127.0.0.1:8420>. The first visit asks you to create the admin account (you).
Then, in **Admin → People**, add an account for your partner (member) and anyone else.
In **Admin → Folders**, set who may see each folder (everyone / chosen people) and at which
level (view, download, edit). Headless alternative: `uv run python -m photo_assistant create-user NAME --role admin`
from `backend/`.

Signing in: pick your name, type your 4-digit PIN. Forgot it? An admin sets a new one in
**Admin → People → Reset PIN**; if the admin forgot theirs, run `just set-pin NAME` on the laptop.

### Wrong PINs: waiting, and a locked account

Wrong PINs are counted per account, whichever phone or computer they come from.

- **Ten wrong PINs within 15 minutes:** the sign-in screen says *"Too many wrong PINs; wait N
  minutes and try again, or ask an admin to unlock this account."* Until then even the right
  PIN is refused. Waiting is enough.
- **Thirty wrong PINs since you last signed in:** the account is **locked**. The sign-in screen
  says *"This account is locked after too many wrong PINs; ask an admin to unlock it, or set a
  new PIN on the server with 'just set-pin'."* Waiting does not help, restarting Photo
  Assistant does not help, and the right PIN is refused. A phone or browser that is still
  signed in keeps working.

Two ways to unlock:

1. **An admin, in the app:** **Admin → People**. The account shows **Locked**; click **Unlock**
   (the PIN stays as it was), or **Reset PIN** to give it a new one, which unlocks it too.
2. **On the laptop:** `just set-pin NAME`. It asks for a new PIN and unlocks the account. This
   is the way back in when the only admin is the one locked out.

Signing in with the right PIN starts both counts again.

## 4c. Optional: AI search and faces

```bash
just models            # downloads the search (CLIP) and face models into the data folder
```

Then restart the app; existing photos are processed in the background. Without the models
everything else works, and Search says the AI part isn't set up yet.

## 5. Update

```bash
cd ~/photo-assistant
git pull
just setup                                  # new dependencies, if any
systemctl --user restart photo-assistant    # or: just install-service (also rebuilds the web app)
just doctor
```

The database is snapshotted automatically before any schema change
(`data/db-backups/`), so an update can always be rolled back. The newest 5 of those
copies are kept; older ones are deleted after an update that worked.

## 6. Next

- Set up backups now: [backups.md](backups.md).
- Phone access over Tailscale: [remote-access.md](remote-access.md).
- Later, moving to the server: [move-to-server.md](move-to-server.md).
