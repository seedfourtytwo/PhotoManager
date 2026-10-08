# Adding cloud and network folders as photo sources

Photo Assistant can bring in photos from MEGA, Proton Drive, your home server (SFTP) or a NAS
(SMB). It *copies* photos from there onto the machine that runs Photo Assistant, then imports
them like any local folder. For MEGA, SFTP and SMB it uses a free tool called **rclone**; for
Proton Drive it uses Proton's own tool, `proton-drive` (see [Proton Drive](#proton-drive)
below, which has its own, shorter steps).

What it will and won't do:

- It only **reads** the cloud or network folder. It never uploads, changes, moves or deletes
  anything there.
- It copies **photos only** (JPEG, HEIC, PNG, RAW, …). Videos and documents are left alone.
- Copies land in `PhotoAssistant/data/staging/<number>/`. Photos you later delete in the cloud
  stay in Photo Assistant. Photos you edit in the cloud come in again as a new version; the
  old one is kept.
- Your password is stored by rclone on this machine, never by Photo Assistant. For Proton
  Drive no password is stored at all: you sign in once in a browser.
- A cloud source belongs to the admin who adds it, exactly like a folder source: everyone can
  see its photos unless you change who may see the source, and a photo you mark **private**
  is hidden from the others.

Every rclone source follows the same three steps: **install rclone → connect the account in
rclone → add it in Photo Assistant.**

---

## Step 1 — install rclone (once)

On the laptop or server that runs Photo Assistant, open a terminal:

```
sudo -v ; curl https://rclone.org/install.sh | sudo bash
rclone version
```

Any recent version works. (Proton Drive does not use rclone: see its own section.)

Optional but recommended: protect rclone's saved passwords with a password of their own.
Run `rclone config`, choose `s) Set configuration password`, and put the same password in
Photo Assistant's `.env` file as `RCLONE_CONFIG_PASS=...` so it can unlock it unattended.

## Step 2 — connect the account in rclone

You give each connection a short **name** (for example `mega`). You will type that exact name
in Photo Assistant later. Pick the section for your service.

### MEGA

1. `rclone config` → `n` (new remote) → name: `mega`
2. Storage type: type `mega` and press Enter.
3. Enter your MEGA email and password when asked. Accept the defaults for everything else.
4. Check it works (this only lists, it changes nothing):
   `rclone lsf "mega:Camera Uploads" --max-depth 1`

Good to know: MEGA may temporarily block accounts that make too many requests. Photo
Assistant is set up to go slowly (about 4 requests a second, 2 files at a time) and to stop and
tell you, rather than retry, if MEGA says "slow down". Just try again an hour later. If your
MEGA account uses two-factor login, check `rclone help backend mega` for your rclone
version: older versions cannot log in to accounts with two-factor login switched on.

### Home server over SFTP (SSH)

Best done with an SSH key, so no password is stored at all.

1. On the server, make the photo folder readable by the account you'll use. Safest: a separate
   account that can *read* the photos but not change them.
2. `rclone config` → `n` → name: `homeserver`
3. Storage type: `sftp`. Host: the server's name or address (e.g. `server.local` or its
   Tailscale name). User: that account. Leave the password empty and, for `key_file`, give the
   path of your private key (e.g. `~/.ssh/id_ed25519`).
4. Check: `rclone lsf homeserver:/srv/photos --max-depth 1`

The **path** you give Photo Assistant is the full folder path on the server, e.g.
`/srv/photos`.

### NAS or shared Windows folder (SMB)

1. `rclone config` → `n` → name: `nas`
2. Storage type: `smb`. Host: the NAS's name or address. User and password: a NAS account that
   can read the photo share (a read-only account is ideal).
3. Check: `rclone lsf nas:photos --max-depth 1` (here `photos` is the *share* name)

The **path** you give Photo Assistant starts with the share name, e.g. `photos/Family`.

Alternative: if the NAS is already mounted on this machine (read-only), you can skip rclone and
add the mounted folder as a normal folder source.

## Step 3 — add it in Photo Assistant

In Photo Assistant, go to **Sources → Add a cloud or network source**, choose the rclone name
you picked (the list shows every name rclone knows), type the folder path (leave it empty for
the whole account), and give it a label such as "MEGA camera uploads". Then press **Pull now**.

The first pull can take hours for a large account; you can keep using the app. Afterwards,
"Rescan all" also pulls every cloud source, and only new or changed photos are copied.

(Until that screen exists, whoever runs the server can do the same with the API:
`POST /api/remote-sources {"label": "...", "remote": "mega", "path": "Camera Uploads"}` and
then `POST /api/remote-sources/<id>/pull`.)

## Proton Drive

Proton Drive does not go through rclone. Photo Assistant uses Proton's own command-line
tool, `proton-drive`, which can read both the **Photos** section (where the Proton phone
app's automatic backup puts pictures) and your normal folders (**My files**).

What it will and won't do, on top of the list at the top of this page:

- **Your Proton password is never typed into Photo Assistant and never stored by it.** You
  sign in once in a browser, on the machine that runs Photo Assistant; Proton's tool keeps
  that sign-in in the system keyring of your user account.
- To bring photos in, Photo Assistant only ever runs four commands of the tool: list the
  Photos timeline, list a folder, download photos, download files. Nothing on Proton is
  changed, moved or deleted.
- Photos only. Videos are left out for now.
- Proton has no "copy only what changed" command, so Photo Assistant keeps its own list of
  what it already fetched (a small file, `data/staging/<number>.proton.json`). If that file is
  lost, the photos are fetched again and recognised as already in the library; nothing is
  doubled.
- It does not work when Photo Assistant runs in Docker (a container has no keyring to hold
  the sign-in): see [move-to-server.md](move-to-server.md).

### 1. Install Proton's tool and sign in (once)

On the laptop or server that runs Photo Assistant, as the user that runs it:

1. Install Proton's `proton-drive` command-line tool, version 0.9.0 or newer, following
   Proton's own instructions. Photo Assistant looks for it on the `PATH` and in
   `~/.local/bin`; if it lives somewhere else, set `PA_PROTON_DRIVE_BINARY` to its full path
   (see [settings.md](settings.md)).
2. Sign in:

   ```
   proton-drive auth login
   ```

   A browser opens; sign in to Proton there (two-factor code included, if you use one).

### 2. Add it in Photo Assistant

**Admin → Sources → Add from Proton.** If the machine is not signed in yet, the dialog says so
and shows the command above; press **Check again** after signing in. Then choose what to
bring in:

- **My Proton photos**: the Photos section.
- **Everything in my Drive**: all of My files.
- **One folder in my Drive**: pick it in the folder list.

Give it a name and press **Add and import**. Later, **Check again** on the source (or
**Check all**) fetches what is new.

Copies land in `PhotoAssistant/data/staging/<number>/` like any cloud source. Each batch is
downloaded into a working folder beside it first and only moved in when complete, so a
half-downloaded photo is never imported and nothing already there is overwritten.

### If a Proton pull goes wrong

The message appears in the source's import history.

| Message says | What to do |
|---|---|
| "is not signed in on this machine" | The sign-in is missing or has expired: run `proton-drive auth login` again, then **Check again**. |
| "proton-drive) is not installed on this machine" | Do step 1, or set `PA_PROTON_DRIVE_BINARY`. |
| "folder … not found on Proton Drive" | The folder was renamed or removed on Proton. Add the source again for the new place. |
| "N files could not be downloaded … (what did arrive was imported)" | Some photos failed this time. **Check again**: only the missing ones are fetched. |
| "took too long and was stopped" | Press **Check again**: photos already pulled are kept. |
| "the disk holding … is full" | Free some space on this machine, then **Check again**. |

### A copy of a backup on Proton Drive

That is a different feature (it *writes* to a folder you choose on Proton): see
[backups.md, section 7](backups.md#7-a-copy-on-proton-drive-off-site).

## When something goes wrong

For rclone sources (MEGA, SFTP, SMB). The message appears in the source's import history.

| Message says | What to do |
|---|---|
| "is not set up on this machine" | The name in Photo Assistant doesn't match rclone. Run `rclone listremotes` and use exactly one of those names. |
| "refused the login" | Password changed or session expired: `rclone config reconnect <name>:` (or edit the remote in `rclone config`). |
| "is limiting requests right now" | The service is throttling. Wait an hour and pull again. |
| "folder … not found" | Check the path with `rclone lsf <name>:` and fix it (paths are case-sensitive). |
| "took longer than … and was stopped" | Just pull again: it continues where it stopped. |
| "rclone is not installed" | Do Step 1. |
