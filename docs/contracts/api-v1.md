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
  with you. Private assets (`private=true` by their owner) are visible only to that owner.
  Effective level on an asset = highest level over its sources (albums grant `view`, plus
  `download` for album editors).
- Pagination: `limit` (1–500, default 200) + opaque `cursor`; response `next_cursor|null`.

## Setup & auth

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/setup` | – | `{needs_admin: bool}` |
| POST | `/api/setup` | `{username, display_name, password}` | `201 User` + session; `409` if users exist |
| POST | `/api/auth/login` | `{username, password}` | `200 User` + session; `401`; `429` after 10 fails/15 min per username+IP |
| POST | `/api/auth/logout` | – | `204` |
| GET | `/api/auth/me` | – | `User` |
| POST | `/api/auth/password` | `{current_password, new_password}` | `204`; `400` if current wrong |

`User = {id, username, display_name, role: "admin"|"member"|"guest", disabled: bool}`.
Passwords ≥ 10 characters. Sessions expire after 30 days idle.

## Users (admin)

| GET | `/api/users` | – | `User[]` |
|---|---|---|---|
| POST | `/api/users` | `{username, display_name, password, role}` | `201 User` |
| PATCH | `/api/users/{id}` | `{display_name?, role?, disabled?, password?}` | `User`; cannot remove the last admin (`409`) |

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
| PATCH | `/api/assets/{id}/state` | `{favourite?, hidden?, private?}` | `AssetOut` (private only by an owner/admin) |
| POST | `/api/assets/state` | `{ids, favourite?, hidden?}` | `{updated}` |
| POST | `/api/assets/dates` | `{ids, set?: "YYYY-MM-DDTHH:MM:SS", shift_minutes?: int}` (exactly one) | `{updated}`; needs `edit`; sets `date_source="manual"`, keeps the previous value |
| GET | `/api/assets/{id}/edit` | – | `Recipe` |
| PUT | `/api/assets/{id}/edit` | `Recipe` | `Recipe`; needs `edit` |
| DELETE | `/api/assets/{id}/edit` | – | `204` (revert) |
| GET | `/api/groups/{group_id}` | – | `AssetOut[]` (a burst / near-duplicate set) |

`Recipe = {rotate: 0|90|180|270, flip_horizontal: bool, flip_vertical: bool,
crop: {x, y, w, h} | null (fractions 0–1 of the rotated image), straighten: -15..15}`.
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
`X-Skipped` header). `original` + no resize streams the untouched file; any other option
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
| POST | `/api/trash/empty` | `{ids?}` | `{purged}` (admin) — removes the library copy and derivatives; never touches sources |

Items in the trash disappear from every listing; after 30 days a job purges them.
A purged photo that still exists in a source is **not** re-imported on rescan (remembered by hash).
