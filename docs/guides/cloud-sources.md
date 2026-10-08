# Adding cloud and network folders as photo sources

Photo Assistant can bring in photos from MEGA, Proton Drive, your home server (SFTP) or a NAS
(SMB). It uses a free tool called **rclone** to *copy* photos from there onto the machine that
runs Photo Assistant, then imports them like any local folder.

What it will and won't do:

- It only **reads** the cloud or network folder. It never uploads, changes, moves or deletes
  anything there.
- It copies **photos only** (JPEG, HEIC, PNG, RAW, …). Videos and documents are left alone.
- Copies land in `PhotoAssistant/data/staging/<number>/`. Photos you later delete in the cloud
  stay in Photo Assistant. Photos you edit in the cloud come in again as a new version; the
  old one is kept.
- Your password is stored by rclone on this machine, never by Photo Assistant.

Every source follows the same three steps: **install rclone → connect the account in rclone →
add it in Photo Assistant.**

---

## Step 1 — install rclone (once)

On the laptop or server that runs Photo Assistant, open a terminal:

```
sudo -v ; curl https://rclone.org/install.sh | sudo bash
rclone version
```

The version must be **1.64 or newer** for Proton Drive (Ubuntu's own `apt install rclone`
package is older and has no Proton support). Any recent version works for the others.

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

### Proton Drive (beta — read this first)

rclone's Proton Drive support is a **beta**. It can read your normal Proton Drive folders
("My files"), but **it cannot see the Photos section** yet — the place where the Proton
iPhone app's automatic photo backup puts pictures. So:

- Photos you (or your partner) put in a normal Proton Drive folder: works, set up below.
- Photos that only exist in Proton's **Photos** section: use one of these workarounds:
  1. **Best for a phone:** set up the free iPhone Shortcut
     ([iphone-shortcut.md](iphone-shortcut.md)) on that phone so new photos go straight to
     Photo Assistant — no Proton step at all.
  2. **For photos already in Proton Photos:** on a computer, open Proton Drive (web or desktop
     app), select the photos in *Photos*, **Download** them to a folder, and add that folder to
     Photo Assistant as an ordinary folder source. Repeat now and then.
  We'll switch to reading Proton Photos directly once rclone or Proton supports it.

Setup for normal folders:

1. `rclone config` → `n` → name: `proton`
2. Storage type: `protondrive`
3. Enter your Proton username (email) and password. If you use two-factor login, enter the
   6-digit code when asked. If you use Proton's "two-password mode", enter the mailbox
   password too.
4. Check: `rclone lsf proton: --max-depth 1`

Proton sometimes asks you to log in again. If Photo Assistant says the login was refused,
run `rclone config reconnect proton:` and enter a fresh code.

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

To have it pulled without asking, set **Check automatically** on its row (Admin → Folders) to
every hour, day or week. The row then says when the next check is. Nothing is ever written to
the cloud folder, and photos removed there stay in the library.

(Until that screen exists, whoever runs the server can do the same with the API:
`POST /api/remote-sources {"label": "...", "remote": "mega", "path": "Camera Uploads"}` and
then `POST /api/remote-sources/<id>/pull`.)

## When something goes wrong

The message appears in the source's import history.

| Message says | What to do |
|---|---|
| "is not set up on this machine" | The name in Photo Assistant doesn't match rclone. Run `rclone listremotes` and use exactly one of those names. |
| "refused the login" | Password changed or session expired: `rclone config reconnect <name>:` (or edit the remote in `rclone config`). |
| "is limiting requests right now" | The service is throttling. Wait an hour and pull again. |
| "folder … not found" | Check the path with `rclone lsf <name>:` and fix it (paths are case-sensitive). |
| "took longer than … and was stopped" | Just pull again: it continues where it stopped. |
| "rclone is not installed" | Do Step 1. |
