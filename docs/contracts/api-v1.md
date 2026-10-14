# API contract v1 (M2)

The shared contract between the backend and the web UI. Both sides are built against this
document in parallel; the backend's OpenAPI output must match it (a contract test checks the
routes exist). Change it only by agreement, in the same PR on both sides.

Conventions
- JSON everywhere; errors are `{"detail": "human sentence"}` with 4xx/5xx.
- Dates: `taken_at` is local wall-clock time, ISO without zone (`2019-07-04T18:30:00`);
  `tz_offset_minutes` may be null. Day filters use `YYYY-MM-DD`.
- Auth: session cookie `pa_session` (HttpOnly, SameSite=Strict, Secure when served over HTTPS),
  kept 30 days. Any authenticated response may set it again with the same value (the server
  does so every 15 days of use, together with its marker cookie `pa_session_fresh`), so a
  session that is used does not end; clients have nothing to do.
  Every `/api/*` route needs a session **except** `/api/health`, `/api/setup` (GET/POST),
  `/api/auth/accounts`, `/api/auth/login`, and the two `/api/sync/…` routes of "Keep on my
  phone", which take a device token instead (v1.7). No session → `401`. Not allowed → `403`. Hidden from you → `404`.
- Roles: `admin` (everything, manages users/sources/access), `member`, `guest`
  (view + download only; never edits).
- Access levels on a source: `view` < `download` < `edit`. Admins have `edit` everywhere.
  You **see** an asset if any source it came from grants you ≥ view, or it is in an album shared
  with you.
- **Private (v1.2, QA A3).** Whoever sets `private=true` is its *marker* (it needs `edit` on the
  photo, from a source or as an admin). A private photo is hidden from everyone who reaches it
  **only** through sources the marker owns or through albums — admins included. The marker
  still sees it, and so does anyone who reaches it through a source the marker does *not* own
  (e.g. the same file is also in the admin's own folder: the admin keeps seeing it there, at the
  level that source gives). Ownership of the first source a photo came from no longer matters.
  Effective level on an asset = highest level over its sources. **Albums grant `view` only**
  (owner, editor or viewer alike): `download` and `edit` come only from sources (admins have
  `edit` everywhere). Changed in v1.2 (QA A1): album editors used to get `download`.
- Pagination: `limit` (1–500, default 200) + opaque `cursor`; response `next_cursor|null`.
- Ids are positive 64-bit integers (v1.2): a larger id in a path is `404`, in a body `422`,
  in `source_id` `400`. `to=9999-12-31` is a valid (open) upper bound.
- A request body over 1 MB (1,000,000 bytes) is refused with `413 {"detail": "request body too
  large"}` before it is parsed (v1.4). `POST /api/upload` is the one exception: it has its own
  per-file limit.

## Setup & auth

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/setup` | – | `{needs_admin: bool}` |
| POST | `/api/setup` | `{username, display_name, pin}` | `201 User` + session; `409` if users exist |
| GET | `/api/auth/accounts` | – | `[{username, display_name}]`: the active accounts, for the login screen to offer (open; names only) |
| POST | `/api/auth/login` | `{username, pin}` | `200 User` + session; `401` wrong PIN or unknown name; `429` wait; `423` account locked (see *Wrong PINs* below) |
| POST | `/api/auth/logout` | – | `204` |
| GET | `/api/auth/me` | – | `User` |
| POST | `/api/auth/pin` | `{current_pin, new_pin}` | `204`; `400` if current wrong (counted like a wrong PIN at login: then `429`, `423`). Ends every **other** session of the user; this one stays (v1.2) |

`User = {id, username, display_name, role: "admin"|"member"|"guest", disabled: bool}`.
A PIN is exactly 4 digits (`422` otherwise). Sessions expire after 30 days idle.

**Wrong PINs** (v1.4) are counted per account, whatever address they come from, at login and
at the PIN change alike. A try is counted before the PIN is checked, so tries sent together
cannot get past a limit.

- **Wait.** After 10 wrong PINs within 15 minutes, every further try on that account, the
  right PIN included, is `429` until the oldest of the ten is 15 minutes old. `detail`:
  `too many wrong PINs; wait N minutes and try again, or ask an admin to unlock this account`.
- **Lock.** After 30 wrong PINs since the account's last good sign-in (no time limit), the
  account is locked: every try, the right PIN included, is `423` until an admin unlocks it
  (`POST /api/users/{id}/unlock`), an admin sets a new PIN (`PATCH /api/users/{id}`), or
  `just set-pin NAME` is run on the server. `detail`: `this account is locked after too many
  wrong PINs; ask an admin to unlock it, or set a new PIN on the server with 'just set-pin'`.
  A restart does not lift it. Sessions that are already open keep working.
- A right PIN starts both counts again. A user name nobody has is `401` at once and is not
  counted.

## Users (admin)

| GET | `/api/users` | – | `ManagedUser[]` |
|---|---|---|---|
| POST | `/api/users` | `{username, display_name, pin, role}` | `201 ManagedUser` |
| PATCH | `/api/users/{id}` | `{display_name?, role?, disabled?, pin?}` | `ManagedUser`; cannot remove the last admin (`409`). A `pin` reset ends **all** the user's sessions and revokes their device tokens (v1.2), and lifts the wait and the lock (v1.4) |
| POST | `/api/users/{id}/unlock` | – | `204`; lifts the wait (`429`) and the lock (`423`) on that account and starts its count of wrong PINs again (v1.3, v1.4); also for the admin's own account; `404` unknown id |

`ManagedUser = User + {locked: bool}` (v1.4). `locked` is true while wrong PINs keep the account
from signing in: locked after 30, or waiting out the 15 minutes after 10. Only these admin
routes carry it: `User` (login, `/api/auth/me`), `/api/auth/accounts` and
`/api/users/directory` never say whether an account is locked.

## Look (v1.5)

Each account has a look: one sheet of named values, never CSS (`docs/adr/0001`). The account
itself chooses only its `mode`; an admin sets the whole sheet of any account.

| GET | `/api/me/look` | – | `Look` of the signed-in account (every role) |
|---|---|---|---|
| PUT | `/api/me/look` | `{mode}` and nothing else | `Look`; every role, guests included. Any other field, or none, is `422` |
| GET | `/api/admin/accounts/{id}/look` | – | `Look` (admin); `404` unknown id |
| PUT | `/api/admin/accounts/{id}/look` | `Look`, any fields left out | `Look` as stored (admin). A field left out goes back to its default, so `{}` resets the look. `404` unknown id |

`Look`, always answered whole:

| Field | Values | Default |
|---|---|---|
| `theme` | `"safelight"`, `"album"` | `"safelight"` |
| `mode` | `"system"` (follow the device), `"dark"`, `"light"` | `"dark"` |
| `accentHue` | whole number 0–360, or `null` (the theme's own) | `null` |
| `corners` | whole number 0–22 (px), or `null` | `null` |
| `photoGap` | whole number 0–8 (px), or `null` | `null` |
| `textScale` | 0.9–1.25, two decimals | `1` |
| `thumbSize` | `"small"`, `"medium"`, `"large"` | `"medium"` |
| `showToday` | `true` / `false` | `true` |
| `startPage` | `"today"`, `"library"` | `"today"` |
| `collectionsRows` | one to three of `"people"`, `"places"`, `"albums"`, each once, in the order shown | all three, in that order |
| `dockLabels` | `true` / `false` | `true` |

Rules (`backend/src/photo_assistant/domain/look.py` is the source; `web/src/lib/look/sheet.ts`
mirrors it by hand; both test suites run the cases in `docs/contracts/look-cases.json`):

- A field that is not in the table is `422`; `detail` names it. So is a value of the wrong
  kind (`"big"` for a number, `1` for a switch) and a choice that does not exist.
- A number outside its range is **clamped**, not refused, however far outside it is (`1e400`
  is the top of the range). It is clamped first and then rounded as the table says, a half
  going up: `2.5` is `3`, a text scale of `1.125` is `1.13`.
- `showToday: false` forces `startPage: "library"`.
- An account with no stored look has the defaults. A stored sheet is read field by field: a
  field that no longer passes these rules (a theme removed in a later version) is answered as
  its default, the rest of the sheet stays, and the account's next mode change keeps it.
  Something stored that is no sheet at all is the defaults. Nothing a sheet holds can make
  the app unusable.
- `PUT /api/me/look` changes the mode of the sheet as it is stored at that moment, in one
  step: an admin's save at the same time is never half undone.
- `showToday` and `startPage` are stored and answered but have no effect until the Today page exists.

## Sources (existing, plus access)

Existing M1 routes stay: `GET/POST /api/sources`, `PATCH /api/sources/{id}`,
`POST /api/sources/{id}/scan`, `POST /api/sources/scan-all`, `GET /api/imports`,
`GET /api/imports/{id}`, `GET /api/jobs`, `POST /api/jobs/{id}/retry`, `GET /api/stats`.
Adding/scanning sources is admin-only. `SourceOut` gains `owner_id` and `asset_count`.
Since v1.2 `SourceOut.path` (the folder on the server) is `null` for everyone but admins, and
`SourceOut.problem` is `"folder not found"` when the folder is gone (else `null`). A scan of
such a source fails visibly: its import run is `failed` with that message, and the scan job
is `failed` without retries.
A job that failed and will be tried again stays `queued` with `run_after` (UTC ISO time, else
`null`) and its last `error`; `GET /api/stats` counts such jobs under `jobs.waiting`, not
under `jobs.queued`. `GET /api/jobs` with `status=waiting` lists just those jobs (the admin screen
shows them with the time of the next attempt); `status=queued` still lists every queued job.

`PATCH /api/sources/{id}` (admin) takes `{enabled?, label?, owner_id?}` and answers the
`SourceOut`; only the fields sent change. `label` (1–100 characters) renames the source
(v1.4). An unknown `owner_id` is `422`.

`GET /api/imports` (admin; `?source_id=` for one source) lists the newest 200 runs, newest
first (v1.4): older runs are not returned.

`GET /api/imports/{id}` (admin) answers one page of the run's files:
`{id, source_id, status, message, summary, items: [{relative_path, outcome, reason, asset_id}],
total, limit, offset, next_offset}`. Query: `outcome` (only that outcome), `limit` (default 500,
1–2000, else `422`), `offset` (default 0). `items` list what needs a look first — `failed`,
`skipped`, `duplicate`, then `already_known` and `imported` — and within an outcome the order
the run handled them. `total` counts the files of the asked outcome (all, without `outcome`);
`next_offset` is the `offset` of the next page, `null` on the last. `summary` is always the whole
run's counts. A run of up to 500 files answers as before, plus the four paging fields.

**Automatic re-checks.** `SourceOut.recheck` is `off` (default), `hourly`, `daily` or `weekly`;
`PATCH /api/sources/{id}` takes `{recheck}` (admin; any other value `422`). Every few minutes
the server queues the ordinary scan job for each enabled source whose last check *started* at
least that long ago (a failed check counts, so it is not retried at once), unless one is
already waiting or running. `SourceOut.next_check_at` is when that is next due: `null` when
off or disabled, possibly a moment already past (it runs at the server's next look).

| GET | `/api/sources/{id}/access` | – | `Access` (admin; v1.2 — members `403`) |
|---|---|---|---|
| PUT | `/api/sources/{id}/access` | `Access` | `Access` (admin) |

`Access = {everyone: null|"view"|"download"|"edit", users: [{user_id, level}]}`.
New sources default to `{everyone: "download", users: []}`.

## Assets

`GET /api/assets` — the timeline, newest first. Query filters (all optional, combinable):

| param | meaning |
|---|---|
| `from`, `to` | inclusive day range `YYYY-MM-DD` |
| `year`, `month` | shortcuts (month needs year) |
| `source_id` | repeatable; only sources you can see count (a hidden source's id selects nothing, v1.2) |
| `camera` | exact `camera_model` |
| `place` | matches country, region or city (case-insensitive) |
| `q` | free text over file names (in sources you can see, v1.2), place names, camera, album titles (of albums you can see) |
| `favourite` | `true` = only my favourites |
| `hidden` | `true` = only my hidden; default hides them |
| `guessed_date` | `true` = only photos whose date came from the file (`file_mtime`) |
| `has_location` | `true`/`false` |
| `trashed` | never listed here (see Trash) |

`AssetOut` (list item):
```
{id, taken_at, tz_offset_minutes, date_source, width, height, kind,
 thumb: {url} | null, preview_ready, favourite, hidden, private,
 place: {country, region, city} | null, edited: bool, variant_of: id|null,
 group_id: id|null}          # bursts / near-duplicates share a group
```
`thumb.url` and preview URLs include `?v=<edit version>` so browsers re-fetch after an edit.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/assets/facets` | same filters | `{years:[{year,count}], sources:[{id,label,count}], cameras:[{name,count}], places:[{name,count}], guessed_dates:int, total:int}` |
| GET | `/api/calendar` | same filters | `[{day:"YYYY-MM-DD", count}]` |
| GET | `/api/map` | same filters | `[{id, lat, lon}]` |
| GET | `/api/assets/{id}` | – | `AssetDetail` = AssetOut + `{name, byte_size, mime_type, camera_make, camera_model, latitude, longitude, f_number, exposure_time, iso, focal_length, imported_at, origins:[{source_id, source_label, relative_path}], albums:[{id,title}], level}`. The four exposure values (v1.6) are each a number or `null`: `f_number` 2.8 for f/2.8, `exposure_time` in seconds (0.004 for 1/250), `iso` a whole number, `focal_length` in millimetres (the lens's own, not the 35 mm equivalent) |
| GET | `/api/assets/{id}/thumb` · `/preview` | – | WebP, edit applied |
| GET | `/api/assets/{id}/original` | – | untouched original (needs `download`) |
| PATCH | `/api/assets/{id}/state` | `{favourite?, hidden?, private?}` | `AssetOut` (`private` needs `edit`; see Private above) |
| POST | `/api/assets/state` | `{ids, favourite?, hidden?}` | `{updated}` |
| POST | `/api/assets/dates` | `{ids, set?: "YYYY-MM-DDTHH:MM:SS", shift_minutes?: int}` (exactly one) | `{updated}`; needs `edit`; sets `date_source="manual"`, keeps the previous value. `422` if a photo would end up more than a day after the server's local now (v1.2) |
| GET | `/api/assets/{id}/edit` | – | `Recipe` |
| PUT | `/api/assets/{id}/edit` | `Recipe` | `Recipe`; needs `edit` |
| DELETE | `/api/assets/{id}/edit` | – | `204` (revert) |
| GET | `/api/groups/{group_id}` | – | `AssetOut[]` (a burst / near-duplicate set) |

`Recipe = {rotate: 0|90|180|270, flip_horizontal: bool, flip_vertical: bool,
crop: {x, y, w, h} | null (fractions 0–1 of the rotated image; `w`, `h` ≥ 0.001 since v1.2),
straighten: -15..15}`.
One recipe per photo, shared by everyone (needs `edit`). Originals never change.

## Downloads

| POST | `/api/downloads/estimate` | `DownloadRequest` | `{count, bytes}` — from each photo's real size: exact for untouched originals, calibrated factors for conversions (v1.2; see docs/PERFORMANCE.md) |
|---|---|---|---|
| POST | `/api/downloads` | `DownloadRequest` | streamed `application/zip`, named after its scope (v1.3, below) |
| GET | `/api/assets/{id}/download` | query: `format, quality, max_edge, strip_location` | the single file |

```
DownloadRequest = {
  ids?: [id], album_id?: id, filters?: {…same as /api/assets query…},   # exactly one scope
  format: "original"|"jpeg"|"png"|"webp", quality: 1..100 (default 90),
  max_edge: int|null, strip_location: bool, strip_all_metadata: bool,
  naming: "name"|"original"|"date" (default "name"), folders: "flat"|"year"|"month"
}
```
Needs `download` on every included asset (others are silently left out and counted in the
`X-Skipped` header). `max_edge` is 1–20000 (`422` otherwise, v1.2). A photo that fails while
the ZIP is being produced (missing library file, render error) is left out and the stream
goes on; the archive then ends with a `manifest.txt` entry listing each left-out file and why
(`X-Skipped` is sent before streaming starts, so it only counts access) (v1.2). `original` + no resize streams the untouched file; any other option
renders via libvips with the edit recipe applied.

**Photo names (v1.7).** `AssetDetail.name` is the photo's display name (FEATURES 4b.10, `domain/display_name.py`): computed per viewer, never stored. `/api/assets/{id}/original`, `/api/assets/{id}/download` and ZIP entries with `naming: "name"` are named `<name><extension>`, the extension the original's own (or the output format's).

**ZIP name (v1.3).** `Content-Disposition: attachment; filename="<ASCII>"; filename*=UTF-8''<name>`
(RFC 6266/5987). `<name>` is: `album_id` → `<album title>.zip`; `filters` →
`photos-<words>.zip` (`photos-all.zip` with no filter); `ids` → `photos-<n>.zip` (`n` = distinct ids
asked for). Filter words, in this order, lowercase, joined by `-`: day range (`2019-07-04`,
`2019-07-01-to-2019-08-31`, `from-…`, `to-…`), `year[-month]` (`2019`, `2019-07`),
`<n>-source(s)`, camera, place, `q` (each slugged: runs of non-letters/digits → `-`),
`favourites`, `hidden`, `guessed-dates`, `with-location`/`without-location`. E.g.
`{year: 2019, place: "France"}` → `photos-2019-france.zip`. Names are sanitised (no `/ \ : * ? " < > |`
or control characters → `_`; blank titles → `album.zip`) and at most 100 characters. The ASCII
`filename` drops accents and turns other non-ASCII characters into `_`. Single-photo downloads
use the same header shape.

## Albums

| GET | `/api/albums` | – | `AlbumSummary[]` = `{id, title, description, cover:{url}|null, count, owner_id, role:"owner"|"editor"|"viewer", updated_at}` |
|---|---|---|---|
| POST | `/api/albums` | `{title, description?, asset_ids?}` | `201 AlbumSummary` |
| GET | `/api/albums/{id}` | – | `AlbumSummary + {items: AssetOut[]}` in album order |
| PATCH | `/api/albums/{id}` | `{title?, description?, cover_asset_id?}` | `AlbumSummary` |
| DELETE | `/api/albums/{id}` | – | `204` (owner/admin; photos stay in the library) |
| POST | `/api/albums/{id}/items` | `{asset_ids, position?}` | `{count}` — `position` is an index in the items **you** see (default: the end); photos already in the album are skipped, not moved. Undo of a removal: post each photo back at its old index, smallest first (v1.2: a removed cover comes back as the cover) |
| DELETE | `/api/albums/{id}/items` | `{asset_ids}` | `{count}` |
| PUT | `/api/albums/{id}/order` | `{asset_ids}` (full order) | `204` |
| GET/PUT | `/api/albums/{id}/members` | `[{user_id, role:"viewer"|"editor"}]` | same |

## Trash

| DELETE | `/api/assets` | `{ids}` | `{trashed}`; needs `edit` |
|---|---|---|---|
| GET | `/api/trash` | – | `AssetOut[] + trashed_at`. Their `/api/assets/{id}/thumb` and `/preview` keep working for whoever sees them here (v1.2); detail, original and downloads do not |
| POST | `/api/trash/restore` | `{ids}` | `{restored}` |
| POST | `/api/trash/empty` | `{ids?}` | `{purged}` (admin) — removes the library copy and derivatives; never touches sources. Only photos the caller sees in the trash are purged (v1.2); a photo restored meanwhile is kept |

Items in the trash disappear from every listing; after 30 days a job purges them.
A purged photo that still exists in a source is **not** re-imported on rescan (remembered by hash).

---

# v1.1 additions (M2 integration)

Backwards compatible: nothing in v1 changed meaning. Same conventions (JSON, `{detail}` errors,
session cookie, 401/403/404 rules). Every route below needs a session unless it says otherwise.

## Contract gaps closed for the web app

| Method | Path | Body / query | Response |
|---|---|---|---|
| POST | `/api/downloads` | `DownloadRequest` as JSON **or** a form (`application/x-www-form-urlencoded` / `multipart/form-data`) whose field `request` holds that JSON | streamed `application/zip` (as v1). A missing or invalid `request` field is `422`. The cross-site guard still applies, so only same-origin forms work. |
| GET | `/api/assets/{id}/preview` | `?edit=none` | the preview **without** the edit recipe (the editor's base image); any other `edit` value is `422` |
| GET | `/api/users/directory` | – | `[{id, display_name}]` to share albums with: members see active accounts, admins see every account, guests `403`. No usernames or roles. |

**Edit geometry** (unchanged, now tested on both sides): rotate (quarter turns, clockwise) →
flip (in the rotated frame) → straighten (clockwise, zoomed just enough to hide the empty
corners) → crop (fractions of that frame). `web/src/lib/crop.ts` and the libvips renderer
render the same pixels (`backend/tests/adapters/test_edit_parity.py`).

## Upload and device tokens

Auth: the session cookie **or** `Authorization: Bearer <device token>`. A presented bearer token
must be valid (a bad one is `401`, never a fallback to the cookie). Disabled accounts `401`,
guests `403`. Uploads land in the uploader's own inbox source (kind `inbox`, owned by them,
access `{everyone: null, users: [{owner, edit}]}`: **private to the uploader** until shared).

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/upload` | session or device | multipart, any field name, many files | `{files: [{name, outcome: "stored"\|"duplicate"\|"rejected", stored_as, content_hash, asset_id, reason}], import_job_id\|null}`; `400` broken multipart, `415` not multipart. `duplicate` = you already have it (or it was purged); `asset_id` is only ever the id of a photo you can see, else `null` (v1.2) |
| POST | `/api/upload/check` | session or device | `{hashes: [blake3 hex]}` (≤ 5000) | `{missing: [...]}` — missing **for you** (v1.2): purged photos count as present; a photo that exists but is hidden from you is missing (uploading it links the existing photo to your inbox: one library copy, and you gain access through your inbox) |
| GET | `/api/upload/jobs/{import_job_id}` | session or device | – | `{id, status: "queued"\|"running"\|"done"\|"failed", run_after}`: the import your own upload queued (`import_job_id` of `POST /api/upload`). `run_after` (UTC time, else `null`) is set while a failed import waits for its next attempt. Any other job, anyone else's upload and an unknown id are all `404` (admins too: they have `GET /api/jobs`); guests `403`. The web app waits for this job after an upload, not for the whole queue. |
| GET | `/api/devices` | session | – | `[{id, name, platform, created_at, last_used_at, last_sync_at, revoked}]` (`last_sync_at` v1.7: when it last asked for its "Keep on my phone" list) |
| POST | `/api/devices` | session | `{name, platform: "ios"\|"android"\|"desktop"\|"other"}` | `201 {device, token}` (the token is shown once) |
| DELETE | `/api/devices/{id}` | session | – | `204`; `404` if not yours |

Limits: `PA_UPLOAD_MAX_MB` per file (default 200), `PA_UPLOAD_MAX_FILES` per request (500).
Photos only (sniffed by their bytes); videos are refused for now.

While the library disk has less free space than `PA_MIN_FREE_GB`, files are refused before a
byte of them is stored (v1.4). The answer is still `200`: each such file comes back with
`outcome: "rejected"` and a `reason` that says so ("the library disk is almost full (… GB
free; uploads keep at least … GB free): free up space on the server, then send it again"),
and `import_job_id` is `null` when nothing was stored.

## Keep on my phone (v1.7)

Server → device, one way (FEATURES 10.6). Each device has its own rules: an album, a person or
filters, each kept on it (`include`) or off it (`exclude`). Its **list** is every photo some
include names minus every photo some exclude names, each once, and only photos its owner may
**download** (an album grants view only, so a shared album's photos go only where a source
gives download) and has not hidden; nothing in the trash or held for review. The list follows
the library: it is computed on every request. What the device deletes is **not** deleted here.

Rules are chosen from a signed-in browser (session only; a device token gets `401`; guests
have no devices). `404` for a device that is not yours or is revoked.

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/devices/{id}/sync` | session | – | `{device: Device, rules: [Rule], count, bytes, sent}`: the list's size, and how many of it the phone said it saved |
| POST | `/api/devices/{id}/sync/rules` | session | `{kind: "album"\|"person"\|"filter", mode: "include"\|"exclude", album_id?, person_id?, filters?}` | `Rule`. Naming the same thing again changes its mode (same `id`). `filters` is the `/api/assets` query as JSON (as in downloads; search facets such as `tag:screenshot` or `person:Lea` go in `q` and mean what they mean in search, words matched without ranking). `404` an album or person you cannot see, `422` a rule that names the wrong thing or more than 50 rules, `400` filters that make no sense |
| DELETE | `/api/devices/{id}/sync/rules/{rule_id}` | session | – | `204`; `404` |
| POST | `/api/devices/{id}/sync/resend` | session | – | `{forgotten}`: the photos the phone said it saved count as new again |

`Rule` = `{id, kind, mode, album_id, person_id, filters, label, count, gone, view_only}`:
`label` is the album's title or the person's name (`null` for filters: the app describes them),
`count` the photos it names that you can see, `gone` true when it names nothing you can see any
more, `view_only` (includes only, else 0) how many of them you may only view, so they can't go
to the phone (typically an album shared with you whose photos no source lets you download).

The device reads its list with its own token, `Authorization: Bearer <device token>` and
nothing else (a session gets `401`). It changes nothing in the library; it only says which
photos it saved. A run killed between fetching and saving offers those photos again, and the
`hash` in the manifest lets a phone skip one it already has.

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/sync/manifest` | device | query `new`, `after`, `limit` | `{device, total, total_bytes, remaining, items: [{id, hash, name, taken_at, bytes, mime_type, url}], next_after}`, in id order. `new=true`: only photos the phone has not said it saved. `limit` 1–200 (default 50); `next_after` (else `null`) is the `after` of the next page. Records `last_sync_at` |
| GET | `/api/sync/assets/{id}/original` | device | – | the untouched original, `Content-Disposition` with its file name (the photo's display name, as in downloads); `404` for a photo not on this device's list (whatever else its owner may see). Fetching marks nothing |
| POST | `/api/sync/sent` | device | `{ids: [id]}` (1–200) | `{sent}`: the phone saved these, so `new=true` leaves them out from now on. Every id must be on this device's list, else `422` and nothing is marked. Saying it again is harmless |

## Remote sources (admin)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/remote-sources/remotes` | – | `{remotes: [name]}`; `503` without rclone |
| POST | `/api/remote-sources` | `{label, remote, path}` | `201 {id, label, remote, path}`; `422` unknown/unsafe remote |
| POST | `/api/remote-sources/{id}/pull` | – | `202 {job_id, source_id}` |

A remote source is an ordinary source of kind `rclone` (default access, like any new source);
`POST /api/sources/{id}/scan` pulls it read-only (`rclone copy`) into `staging/` and imports.
Its `owner_id` is the admin who added it (v1.4), as for a folder source; the same holds for a
Proton Drive source (`POST /api/proton/sources`, kind `proton`).

## Local ML (search, similar photos, people)

All results are limited to what you may see (the same visibility rule as the timeline).
Without model files every route still answers; nothing fails because a model is missing.

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/api/search` | `q` (free text + facets `date:2023[-07[-04]]`, `person:Lea`, `tag:beach`, `place:"Le Havre"`, `camera:X100`), `limit` ≤ 200, plus any `/api/assets` filter | `{items: (AssetOut + {score})[], text, facets: [{name, value}], mode: "semantic"\|"text"\|"filter", detail}`. With the CLIP model, free text is ranked by meaning (`mode: semantic`, `score` = cosine). Without it, free text falls back to the v1 word search (`mode: text`, `detail: "models not installed: …"`). Facets only: `mode: filter`, newest first. `400` for an impossible date facet. |
| GET | `/api/assets/{id}/similar` | `limit` ≤ 200 | `(AssetOut + {score})[]`; `503` models not installed; `409` not analysed yet |
| GET | `/api/assets/{id}/faces` | – | `[{id, asset_id, box: {x, y, w, h}, score, person_id}]` (box in fractions of the displayed photo) |
| GET | `/api/assets/{id}/tags` | – | `{tags: [{name, score}], screen_or_document: bool\|null}` |
| GET | `/api/people` | `hidden` (default `false`) | `[{id, name, face_count, asset_count, hidden, cover: Face\|null, portrait: Portrait\|null}]` (counts over what you may see). The people listed; `hidden=true` answers the ones hidden from the list instead. `Portrait` = `{face_id, asset_id, cx, cy, size, chosen, url}`: the person's round picture as a circle on photo `asset_id` as displayed without its edits (`cx`, `cy`: the centre as fractions of the width and height; `size`: the square round it as a fraction of the shorter edge). `chosen: false` is the automatic circle round the face. `url` is the picture, ready to use; it changes whenever the picture does, so it can be cached for good. A portrait is only ever from a photo you may see: if the chosen one is not, you get the automatic one of the best face you may see |
| GET | `/api/people/{id}` | – | `Person`; `404` |
| PATCH | `/api/people/{id}` | `{name?, hidden?}` | `Person` (members/admins; guests `403`). Only what is sent changes; `name: null` takes the name away; an empty body is `422`. A hidden person keeps their faces, so later photos of them join the same person; they still open by id and are still found by `person:Name` |
| GET | `/api/people/{id}/portrait` | `v` (from `url`) | `image/webp`, a square of at most 320 px cut from the original: your portrait of that person. `404` no such person for you, or the original is missing |
| PUT | `/api/people/{id}/portrait` | `{face_id, cx, cy, size}` | `Person` (members/admins; guests `403`). The face must be that person's, on a photo you may see (`404`). Numbers outside the photo are brought inside it; `422` for what is not a number. One portrait for everyone who may see that photo |
| DELETE | `/api/people/{id}/portrait` | – | `Person` (guests `403`): the automatic circle again, on the same photo |
| GET | `/api/people/{id}/faces` | `limit` ≤ 100 (default 24) | `Portrait[]`: that person's faces on photos you may see, the best first, each as its automatic portrait with its own `url` |
| GET | `/api/faces/{id}/portrait` | `v` (from `url`) | `image/webp`: the automatic portrait of one face; `404` unless you may see its photo |
| POST | `/api/people/{id}/merge` | `{source_ids}` | `Person` (guests `403`) |
| POST | `/api/people/split` | `{face_ids, person_id?, name?}` | `Person` (no `person_id` → a new person; guests `403`) |
| GET | `/api/people/{id}/assets` | `limit`, `cursor` | `{items: AssetOut[], next_cursor}` newest first |
| GET | `/api/ml/status` | – | `{clip: {ready, detail}, faces: {ready, detail}, models_installed, counts: {task: {status: n}}}` |
| POST | `/api/ml/backfill` | – | `{queued, detail}` (admin) — run after `just models` |

## Album → print

Printing puts full-resolution pixels in a file, so it needs `download` on **every** photo of the
album you can see (`403` otherwise); albums hidden from you are `404`.

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/api/print/options` | – | `{trims: [{id, label, width_mm, height_mm}], themes: [{id, label, paper, ink, font}], layouts: [{id, label, capacity}]}` |
| POST | `/api/albums/{id}/print/plan` | `PrintRequest` | `{pages: [{layout_id, photos: [asset_id], text}], issues: [{asset_id, ppi, level: "warn"\|"block"}], page_count}` (cover included in `page_count`; nothing is rendered) |
| POST | `/api/albums/{id}/print` | `PrintRequest` | `200 application/pdf` (`Content-Disposition: attachment; filename="<title>.pdf"`, `X-Print-Warnings: n`); `422 {detail, issues}` when a photo is too small and `allow_low_resolution` is false |
| GET | `/api/albums/{id}/print/preview` | `page` (1-based; the cover is page 1), `trim`, `theme`, `cover`, `ppi` (24–300, default 96) | `200 image/png`; `422` for a page outside the album |

```
PrintRequest = {trim: "a4-landscape", theme: "quiet", cover: true, crop_marks: false,
                pages?: [{layout_id, asset_ids: [id], text?}],   # manual layout; omit = automatic
                allow_low_resolution?: false}
```
Unknown trim, theme or layout, or a page whose photo count doesn't fit its layout: `422`.
Caps (v1.4, `422` beyond them): at most 10,000 `pages`; at most 4 `asset_ids` on a page (the
largest layout); `text` up to 5,000 characters; `trim`, `theme` and `layout_id` up to 40
characters.
Each sheet is the trim plus 3 mm bleed per side (plus a 10 mm slug with crop marks).

## Folders of the server (admin)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/folders` | `path?` (default: the home folder) | Admin. `{path, parent?, folders: [{name, path}], truncated, roots: [{label, path}], source_problem?}`: the sub-folders of one folder on the server, to pick one. Hidden folders and the library's own folder are never listed; `422` with the reason for a path that is not absolute, has control characters, is missing or unreadable, or is inside the library. `source_problem` says why this folder can't be added as a source |

## Backups (admin)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/backups` | – | `[Target]` with `last_run`, `next_run_at`, `overdue`, `last_proven_at` (last restore test that matched every hash), `restore_failing`, `key_saved`, `needs_attention` (drives the banner: overdue, a failed backup or restore test, or an unconfirmed recovery key), `skipped_since` (the latest run was skipped because the disk was not connected: when it started; else null), `mirror_overdue` (the Proton copy has no fresh success) |
| GET | `/api/backups/health` | – | `{protected, places_ok, places_total, problems: [{severity: "alert"\|"warning", message, target_id?}]}`. Read-only, admin only. `protected` = at least two healthy backup places (a repository, or its Proton copy, each count); `target_id` null = about the library as a whole |
| GET | `/api/backups/places` | – | `{library_bytes, disks: [{path, label, free_bytes}], remotes: [name]}`: plugged-in disks and rclone remotes |
| POST | `/api/backups/plan` | `{place}` (a folder path, or `rclone:<remote>:<folder>`) | `{repository, library_bytes, free_bytes?, ok, problem?, warnings}`. Creates nothing. Refused (`ok: false`): not enough room, not writable, inside the library or a source folder, another backup already there |
| POST | `/api/backups/setup` | `{label, place, schedule?, retention?}` | `201 {target: Target, recovery: {label, repository, key}}`. Makes the key, queues the first backup (followed by a restore test). `422` with the plan's problem, `409` for a taken name |
| GET | `/api/backups/{id}/recovery` | – | `{label, repository, key}`; `409` if the key file is gone, or lies outside the app's key folder (v1.4: such a target was added on the command line, and its key is only shown there) |
| POST | `/api/backups/{id}/key-saved` | – | `Target`: the admin confirms a copy of the key exists elsewhere |
| POST | `/api/backups` | `{label, repository, password_file, schedule?, quiet_window?, retention?: {daily, weekly, monthly}}` | `201 Target`; `422` when `password_file` is not a key file in the app's key folder (`PA_BACKUP_KEY_DIR`), whether or not the file exists (v1.4; a password file elsewhere on the server can only be used from the command line, `just backup add`) |
| PATCH | `/api/backups/{id}` | `{enabled?, schedule?, quiet_window?, retention?: {daily?, weekly?, monthly?}}` | `Target`. Only the fields sent change (v1.3); `quiet_window: null` = any time; retention counts merge into the current ones. Bad schedule/window/retention or an unknown field: `422`, nothing changed |
| POST | `/api/backups/{id}/run` · `/restore-test` | – | `202 {job_id, target_id}` |
| GET | `/api/backups/{id}/runs` | `limit` | `[Run]` |

---

# v1.2 changes (fix/backend, after the M2 QA)

Each change is also written next to the route it concerns above. For the web app:

| Area | Change | Web impact |
|---|---|---|
| Access | Albums grant **view only** (editor/owner included); download and edit come only from sources. | An album editor may now get `403` on originals/downloads of album photos: hide "Download" when `level` is `view`. |
| Access | `private` is set by a *marker* (needs `edit`); it hides the photo only from people who reach it solely through the marker's own sources or albums. | None (the `private` flag is unchanged). |
| Access | `GET /api/sources/{id}/access` is admin-only (`403` for others); `SourceOut.path` is `null` for non-admins. | Don't show folder paths or access lists to members. |
| Sources | `SourceOut.problem`: `"folder not found"` or `null`. A scan of a vanished folder records a `failed` import run with that message. | Show `problem` next to the source; show failed runs. |
| Auth | PIN change ends the user's *other* sessions; an admin reset ends all of them and revokes device tokens. | After an admin reset the user must sign in again (their phone too). |
| Upload | `/api/upload/check` answers for **you**: purged = present; hidden from you = missing (an upload links it to your inbox). `asset_id` is `null` unless you can see that photo. | None. |
| Trash | `POST /api/trash/empty` purges only what you see in the trash; trashed photos keep their `thumb`/`preview` URLs for those who see them there. | Trash thumbnails now load. |
| Albums | `POST /api/albums/{id}/items` `position` counts the items you see; removing the cover keeps it remembered (an undo restores it). | Undo: post each removed photo back at its old index, smallest first. |
| Downloads | `max_edge` 1–20000 (else `422`); a crop must keep ≥ 1/1000 of each side; a failing photo is left out of a ZIP and listed in a final `manifest.txt`; estimates are calibrated. | Possibly show `manifest.txt` hint; estimates are now realistic. |
| Dates | Set/shift that lands more than a day after the server's local now: `422`. | Show the `detail`. |
| Errors | Ids beyond 2^63−1: path `404`, body `422`, `source_id` `400`. The cross-site guard answers `{"detail"}` JSON. `to=9999-12-31` is valid. | None. |
| Transport | JSON responses ≥ 1 KiB are gzip-encoded when asked (`Accept-Encoding`); images, ZIPs and PDFs never. `/_app/immutable/*` is cached for a year. The `/api/map` shape is unchanged. | None (browsers decode gzip). |
| ML | ML jobs are only queued when model files are installed; `/api/ml/backfill` queues `0` (with `detail`) without them. | `ml/status` counts stay empty without models. |

---

# v1.3 changes (fix/asks)

Backwards compatible. Each change is also written next to its route above.

| Area | Change | Web impact |
|---|---|---|
| Downloads | The ZIP is named after its scope: `<album title>.zip`, `photos-<filter words>.zip`, `photos-<n>.zip`; `filename*` (UTF-8) plus a sanitised ASCII `filename`. | Read the name from `Content-Disposition` (`filename*` first) if the app ever saves the blob itself; a form post already gets the right name. |
| Backups | `PATCH /api/backups/{id}` also takes `schedule`, `quiet_window` (null clears) and partial `retention`; `enabled` is optional. | Edit form for an existing target (`api.updateBackup`). |
| Users | `POST /api/users/{id}/unlock` (admin) clears the 10-fails/15-min login block for that account; `204`. | "Unlock" action on the users page (`api.unlockUser`). |

---

# v1.4 changes (QA follow-ups, PIN guessing)

`429` at login no longer depends on the address, and there is a new status, `423`. Each change
is also written next to its route above.

| Area | Change | Web impact |
|---|---|---|
| Auth | Wrong PINs are counted per account, from all addresses together (was: per user name and address). The `429` `detail` says how many minutes to wait. | Show the `detail`. |
| Auth | New: `423` from `POST /api/auth/login` and `POST /api/auth/pin` once an account has 30 wrong PINs since its last good sign-in. The right PIN is refused too, until an admin unlocks the account or it gets a new PIN. | Show the `detail` on the sign-in screen and in Settings. |
| Users | `GET/POST /api/users` and `PATCH /api/users/{id}` answer `ManagedUser` (`User` plus `locked`). Unlock and a PIN reset lift the wait and the lock. | People shows "Locked" and offers Unlock on locked accounts only (`ManagedUser` in `api/types.ts`). |
| Transport | A request body over 1 MB is `413` (`/api/upload` excepted). | None: no request of the web app comes near it. |
| Sources | `PATCH /api/sources/{id}` applies `label`. | Rename a source in place. |
| Sources | A cloud source (rclone, Proton Drive) has the admin who added it as `owner_id`; older ones were given to the first admin. | None (`owner_id` was `null` before). |
| Imports | `GET /api/imports` returns the newest 200 runs. | None. |
| Imports | After a cloud pull where some files failed, the note ("N files could not be downloaded …") is the `message` of the import's own run, whose `status` stays what the import made it; there is no separate `failed` run for it. | The report dialog shows it ("Finished: …"). The Sources list shows a run's `message` only for a `failed` run: not shown there yet. |
| Upload | Files arriving while the disk is under its free-space floor are `rejected` with a reason (status stays `200`). | Show each file's `reason`. |
| Print | Caps on `PrintRequest`: pages, photos a page, text and id lengths (`422`). | None: the editor cannot build a larger request. |
| Backups | `POST /api/backups` refuses a `password_file` outside the key folder (`422`); the recovery sheet answers `409` for a key outside it. | None: guided setup makes its keys in that folder. |

---

# v1.5 changes (per-account look, issue 11)

Additions only.

| Area | Change | Web impact |
|---|---|---|
| Look | New: `GET/PUT /api/me/look` and `GET/PUT /api/admin/accounts/{id}/look` (see "Look" above). | The mode switch in Settings saves on the account (`api.setMyMode`); Admin → People has a "Look" form per account (`api.accountLook`, `api.setAccountLook`). The browser's old `pa.theme` setting is removed after the first `GET /api/me/look` that answers; it is sent as the mode first only when that answer is still the defaults (the API does not say whether a look was ever stored, so a sheet equal to the defaults counts as none). |

---

# v1.6 changes (exposure settings in the photo view)

Additions only.

| Area | Change | Web impact |
|---|---|---|
| Assets | `AssetDetail` (`GET /api/assets/{id}`) carries `f_number`, `exposure_time` (seconds), `iso` and `focal_length` (millimetres); each is `null` when the photo does not carry it. The timeline's `AssetOut` rows are unchanged. | The photo bar's second line reads aperture · shutter · ISO · focal length · file name (`$lib/readout`, `$lib/exposure`), with only the values that are there; a photo with none keeps camera · pixel size · file name. The details list them under the camera. A photo imported before this has `null` everywhere until the admin runs `just exposure-backfill`. |

---

# v1.7 changes (Keep on my phone, FEATURES 10.6)

Additions only.

| Area | Change | Web impact |
|---|---|---|
| Devices | `Device` has `last_sync_at`. New: `GET /api/devices/{id}/sync`, `POST /api/devices/{id}/sync/rules`, `DELETE /api/devices/{id}/sync/rules/{rule_id}`, `POST /api/devices/{id}/sync/resend` (see "Keep on my phone" above). | Settings → Phones and devices shows each device's list (what it keeps and leaves off, count, size, last sync) and offers "Leave out screenshots" and "Send everything again"; album, person, library and search screens have "Keep on phone". |
| Sync | New, device token only: `GET /api/sync/manifest`, `GET /api/sync/assets/{id}/original`, `POST /api/sync/sent`. | None: the Apple Shortcut calls them (`docs/guides/keep-on-my-phone.md`). |
