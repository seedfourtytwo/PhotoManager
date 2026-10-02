# API contract v1 (M2)

The shared contract between the backend and the web UI. Both sides are built against this
document in parallel; the backend's OpenAPI output must match it (a contract test checks the
routes exist). Change it only by agreement, in the same PR on both sides.

Conventions
- JSON everywhere; errors are `{"detail": "human sentence"}` with 4xx/5xx.
- Dates: `taken_at` is local wall-clock time, ISO without zone (`2019-07-04T18:30:00`);
  `tz_offset_minutes` may be null. Day filters use `YYYY-MM-DD`.
- Auth: session cookie `pa_session` (HttpOnly, SameSite=Strict, Secure when served over HTTPS).
  Every `/api/*` route needs a session **except** `/api/health`, `/api/setup` (GET/POST),
  `/api/auth/login`. No session → `401`. Not allowed → `403`. Hidden from you → `404`.
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

## Setup & auth

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/setup` | – | `{needs_admin: bool}` |
| POST | `/api/setup` | `{username, display_name, password}` | `201 User` + session; `409` if users exist |
| POST | `/api/auth/login` | `{username, password}` | `200 User` + session; `401`; `429` after 10 fails/15 min per username+IP |
| POST | `/api/auth/logout` | – | `204` |
| GET | `/api/auth/me` | – | `User` |
| POST | `/api/auth/password` | `{current_password, new_password}` | `204`; `400` if current wrong. Ends every **other** session of the user; this one stays (v1.2) |

`User = {id, username, display_name, role: "admin"|"member"|"guest", disabled: bool}`.
Passwords ≥ 10 characters. Sessions expire after 30 days idle.

## Users (admin)

| GET | `/api/users` | – | `User[]` |
|---|---|---|---|
| POST | `/api/users` | `{username, display_name, password, role}` | `201 User` |
| PATCH | `/api/users/{id}` | `{display_name?, role?, disabled?, password?}` | `User`; cannot remove the last admin (`409`). A `password` reset ends **all** the user's sessions and revokes their device tokens (v1.2) |

## Sources (existing, plus access)

Existing M1 routes stay: `GET/POST /api/sources`, `PATCH /api/sources/{id}`,
`POST /api/sources/{id}/scan`, `POST /api/sources/scan-all`, `GET /api/imports`,
`GET /api/imports/{id}`, `GET /api/jobs`, `POST /api/jobs/{id}/retry`, `GET /api/stats`.
Adding/scanning sources is admin-only. `SourceOut` gains `owner_id` and `asset_count`.

| GET | `/api/sources/{id}/access` | – | `Access` |
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
| `source_id` | repeatable |
| `camera` | exact `camera_model` |
| `place` | matches country, region or city (case-insensitive) |
| `q` | free text over file names, place names, camera, album titles |
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
| GET | `/api/assets/{id}` | – | `AssetDetail` = AssetOut + `{byte_size, mime_type, camera_make, camera_model, latitude, longitude, imported_at, origins:[{source_id, source_label, relative_path}], albums:[{id,title}], level}` |
| GET | `/api/assets/{id}/thumb` · `/preview` | – | WebP, edit applied |
| GET | `/api/assets/{id}/original` | – | untouched original (needs `download`) |
| PATCH | `/api/assets/{id}/state` | `{favourite?, hidden?, private?}` | `AssetOut` (`private` needs `edit`; see Private above) |
| POST | `/api/assets/state` | `{ids, favourite?, hidden?}` | `{updated}` |
| POST | `/api/assets/dates` | `{ids, set?: "YYYY-MM-DDTHH:MM:SS", shift_minutes?: int}` (exactly one) | `{updated}`; needs `edit`; sets `date_source="manual"`, keeps the previous value |
| GET | `/api/assets/{id}/edit` | – | `Recipe` |
| PUT | `/api/assets/{id}/edit` | `Recipe` | `Recipe`; needs `edit` |
| DELETE | `/api/assets/{id}/edit` | – | `204` (revert) |
| GET | `/api/groups/{group_id}` | – | `AssetOut[]` (a burst / near-duplicate set) |

`Recipe = {rotate: 0|90|180|270, flip_horizontal: bool, flip_vertical: bool,
crop: {x, y, w, h} | null (fractions 0–1 of the rotated image; `w`, `h` ≥ 0.001 since v1.2),
straighten: -15..15}`.
One recipe per photo, shared by everyone (needs `edit`). Originals never change.

## Downloads

| POST | `/api/downloads/estimate` | `DownloadRequest` | `{count, bytes}` |
|---|---|---|---|
| POST | `/api/downloads` | `DownloadRequest` | streamed `application/zip` |
| GET | `/api/assets/{id}/download` | query: `format, quality, max_edge, strip_location` | the single file |

```
DownloadRequest = {
  ids?: [id], album_id?: id, filters?: {…same as /api/assets query…},   # exactly one scope
  format: "original"|"jpeg"|"png"|"webp", quality: 1..100 (default 90),
  max_edge: int|null, strip_location: bool, strip_all_metadata: bool,
  naming: "original"|"date", folders: "flat"|"year"|"month"
}
```
Needs `download` on every included asset (others are silently left out and counted in the
`X-Skipped` header). `max_edge` is 1–20000 (`422` otherwise, v1.2). A photo that fails while
the ZIP is being produced (missing library file, render error) is left out and the stream
goes on; the archive then ends with a `manifest.txt` entry listing each left-out file and why
(`X-Skipped` is sent before streaming starts, so it only counts access) (v1.2). `original` + no resize streams the untouched file; any other option
renders via libvips with the edit recipe applied.

## Albums

| GET | `/api/albums` | – | `AlbumSummary[]` = `{id, title, description, cover:{url}|null, count, owner_id, role:"owner"|"editor"|"viewer", updated_at}` |
|---|---|---|---|
| POST | `/api/albums` | `{title, description?, asset_ids?}` | `201 AlbumSummary` |
| GET | `/api/albums/{id}` | – | `AlbumSummary + {items: AssetOut[]}` in album order |
| PATCH | `/api/albums/{id}` | `{title?, description?, cover_asset_id?}` | `AlbumSummary` |
| DELETE | `/api/albums/{id}` | – | `204` (owner/admin; photos stay in the library) |
| POST | `/api/albums/{id}/items` | `{asset_ids, position?}` | `{count}` |
| DELETE | `/api/albums/{id}/items` | `{asset_ids}` | `{count}` |
| PUT | `/api/albums/{id}/order` | `{asset_ids}` (full order) | `204` |
| GET/PUT | `/api/albums/{id}/members` | `[{user_id, role:"viewer"|"editor"}]` | same |

## Trash

| DELETE | `/api/assets` | `{ids}` | `{trashed}`; needs `edit` |
|---|---|---|---|
| GET | `/api/trash` | – | `AssetOut[] + trashed_at` |
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
| GET | `/api/devices` | session | – | `[{id, name, platform, created_at, last_used_at, revoked}]` |
| POST | `/api/devices` | session | `{name, platform: "ios"\|"android"\|"desktop"\|"other"}` | `201 {device, token}` (the token is shown once) |
| DELETE | `/api/devices/{id}` | session | – | `204`; `404` if not yours |

Limits: `PA_UPLOAD_MAX_MB` per file (default 200), `PA_UPLOAD_MAX_FILES` per request (500).
Photos only (sniffed by their bytes); videos are refused for now.

## Remote sources (admin)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/remote-sources/remotes` | – | `{remotes: [name]}`; `503` without rclone |
| POST | `/api/remote-sources` | `{label, remote, path}` | `201 {id, label, remote, path}`; `422` unknown/unsafe remote |
| POST | `/api/remote-sources/{id}/pull` | – | `202 {job_id, source_id}` |

A remote source is an ordinary source of kind `rclone` (default access, like any new source);
`POST /api/sources/{id}/scan` pulls it read-only (`rclone copy`) into `staging/` and imports.

## Local ML (search, similar photos, people)

All results are limited to what you may see (the same visibility rule as the timeline).
Without model files every route still answers; nothing fails because a model is missing.

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/api/search` | `q` (free text + facets `date:2023[-07[-04]]`, `person:Lea`, `tag:beach`, `place:"Le Havre"`, `camera:X100`), `limit` ≤ 200, plus any `/api/assets` filter | `{items: (AssetOut + {score})[], text, facets: [{name, value}], mode: "semantic"\|"text"\|"filter", detail}`. With the CLIP model, free text is ranked by meaning (`mode: semantic`, `score` = cosine). Without it, free text falls back to the v1 word search (`mode: text`, `detail: "models not installed: …"`). Facets only: `mode: filter`, newest first. `400` for an impossible date facet. |
| GET | `/api/assets/{id}/similar` | `limit` ≤ 200 | `(AssetOut + {score})[]`; `503` models not installed; `409` not analysed yet |
| GET | `/api/assets/{id}/faces` | – | `[{id, asset_id, box: {x, y, w, h}, score, person_id}]` (box in fractions of the displayed photo) |
| GET | `/api/assets/{id}/tags` | – | `{tags: [{name, score}], screen_or_document: bool\|null}` |
| GET | `/api/people` | – | `[{id, name, face_count, asset_count, cover: Face\|null}]` (counts over what you may see) |
| GET | `/api/people/{id}` | – | `Person`; `404` |
| PATCH | `/api/people/{id}` | `{name}` | `Person` (members/admins; guests `403`) |
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
Each sheet is the trim plus 3 mm bleed per side (plus a 10 mm slug with crop marks).

## Backups (admin)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/backups` | – | `[Target]` with `last_run`, `next_run_at`, `overdue`, `needs_attention` (drives the banner) |
| POST | `/api/backups` | `{label, repository, password_file, schedule?, quiet_window?, retention?: {daily, weekly, monthly}}` | `201 Target` |
| PATCH | `/api/backups/{id}` | `{enabled}` | `Target` |
| POST | `/api/backups/{id}/run` · `/restore-test` | – | `202 {job_id, target_id}` |
| GET | `/api/backups/{id}/runs` | `limit` | `[Run]` |
