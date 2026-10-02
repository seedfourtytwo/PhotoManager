# Web app wiring (M2)

The web app is a static SvelteKit SPA (`web/`, adapter-static, `ssr = false`). It talks only
to `/api/*` as described in [`docs/contracts/api-v1.md`](../contracts/api-v1.md), through the
typed client in `web/src/lib/api/` (types in `types.ts`, one method per route in `client.ts`).

## Run it

```sh
cd web
pnpm install

# Against the real backend (:8420) — what `just dev` does
pnpm dev

# Against the in-memory mock API (no backend needed)
pnpm mock            # mock API on http://127.0.0.1:8421, sign in as admin / correct horse
pnpm dev:mock        # dev server with /api proxied to the mock

MOCK_USERS=none pnpm mock    # start with no accounts → first-run setup screen
MOCK_COUNT=10000 pnpm mock   # big library, for scrolling/performance checks
```

The dev server proxies `/api` to `PA_API` (default `http://127.0.0.1:8420`). In production the
backend serves `web/build/` itself (`just run`), so the app and API share one origin and the
`pa_session` cookie (SameSite=Strict) just works.

## Tests

```sh
pnpm test            # Vitest: node unit tests + component tests in Chromium
pnpm e2e             # Playwright: desktop 1440×900 and phone 390×844 against the mock
pnpm screenshots     # writes docs/screenshots/integrated/{desktop,phone}-*.png from the mock
```

In containers set `PW_CHROMIUM=/opt/pw-browsers/chromium` (both Vitest browser mode and
Playwright pass it as `executablePath`). `pnpm e2e` starts the mock on :8431 and a dev server on
:5183 itself (override with `E2E_MOCK_PORT` / `E2E_WEB_PORT`), runs with one worker, and resets the
mock (`POST /__mock/reset`, body `{users, count?, models?}`) before each test. `models: true` makes
the mock answer as if the ML models were installed (semantic search, More like this).

### Running the E2E suite against the real backend

`just e2e` seeds a synthetic library, starts the backend in test mode (`POST /__test/reset`)
and runs the whole suite against it. Tests that depend on mock-only behaviour (ML models,
rclone remotes, backups with restic, the mock's scan timing) skip themselves there
(`REAL_BACKEND`). Last run (fix/web against fix/backend, 2 Oct 2026): 93 passed, 27 skipped,
0 failed; against the mock: 109 passed, 11 skipped, 0 failed.

## The mock API (`web/mock-api/`)

Plain `node:http`, no dependencies, run directly by Node 22 type stripping. It implements every
route in the contract in memory: sessions and cookie, 401/403/404 rules, login rate limit,
per-source access and album sharing, filters/facets/calendar/map, cursor paging, recipes
(applied to the SVG thumbs), date fixes, albums, trash, stored-ZIP downloads, and scan jobs that
move queued → running → done over ~3 s and write an import report with skipped/failed/duplicate
reasons. Photos are SVG landscapes drawn from a seed — no real images. `app.spec.ts` exercises
it through the real client, so client and mock agree on every route.

Mock-only routes live under `/__mock/` and are never called by the app.

## Contract assumptions (resolved in the UI; please confirm on the backend)

1. **ZIP download as a form post.** To let the browser stream the ZIP to disk, the app does a
   real `<form method=POST>` into a hidden iframe with **one field `request` holding the
   `DownloadRequest` JSON** (`application/x-www-form-urlencoded`). The backend's
   `POST /api/downloads` should accept that besides a JSON body. The session cookie is sent
   (same origin, SameSite=Strict is fine for a same-origin form post).
2. **Single download options** use `GET /api/assets/{id}/download?format&quality&max_edge&strip_location`
   exactly as in the contract; `max_edge` is omitted for “Original”.
3. **Editor base image.** The editor needs the photo *without* the current recipe to preview
   edits on top of it. It requests `GET /api/assets/{id}/preview?edit=none`. The backend
   should honour `edit=none` (serve the un-edited preview); without it the editor would apply
   the recipe twice.
4. **Recipe geometry.** Applied in this order: quarter-turn `rotate` clockwise, flip in the
   rotated frame, `straighten` clockwise about the centre with the smallest zoom that leaves no
   empty corners (`coverScale` in `web/src/lib/crop.ts`), then `crop` as fractions of that
   frame. libvips rendering must follow the same order to match the preview.
5. **`DateSource` gains `"manual"`** after `POST /api/assets/dates` (the contract says so in
   prose); the UI labels it “date set by hand”.
6. **Facets `places`** may mix countries and cities (the mock returns both); the filter sends
   the chosen name as `place`, which the contract matches against country, region or city.
7. **Map → library.** There is no bounding-box filter. Clicking a cluster lists that cluster's
   photos under the map (fetched via `GET /api/assets?has_location=true`, paged), and “Open in
   library” filters by the cluster's dominant `place` name.
8. **Album sharing for non-admins.** `GET /api/users` is admin-only, so a non-admin album owner
   cannot see names. The share dialog then falls back to adding people by user id and showing
   “User 7”. A small user directory (`GET /api/users/directory` → `[{id, display_name}]` for any
   signed-in user) would fix this — see Asks.
9. **Trash restore** is offered to anyone; the backend decides (the mock restores only photos
   the caller can edit). “Empty trash” is shown to admins only.
10. **Stats/jobs polling.** The admin page polls `GET /api/stats` and `GET /api/jobs?status=failed`
    every 1.5 s while `jobs.queued + jobs.running > 0`, and reloads sources and import runs when
    that drops to zero.

## Screens and behaviour added in the M2 fix round

- **Loupe**: `?photo=<id>` in the URL (reload/share reopens it; Back closes it; closing scrolls
  the grid to that photo and focuses its tile). Chrome fades after 2.5 s and returns on any
  touch, key or mouse movement; a tap on the photo toggles it. The photo area has
  `touch-action: none`, so vertical swipes (up = info, down = close) are not taken by the
  browser. Favourite/Private are optimistic and single-flight. View-only photos show a disabled
  Download with the reason; Edit/Fix date/Private need `edit` (contract v1.2).
- **Grid**: one Tab stop; arrow keys, Home/End move between photos across months.
- **Search** (`/search?q=…`, `/search?like=<id>`), **People** (`/people`, `/people/<id>`: rename,
  merge), **Print** (`/albums/<id>/print`), **Admin → Backups / Cloud folders / Search and
  faces**, **Settings → Phones and devices**.
- **Navigation**: Library · Map · People · Albums · Search everywhere; Trash, Settings, Admin in
  the rail's foot on a laptop and under “More” on a phone. The phone selection bar keeps three
  actions and puts the rest under “More”.
- **Downloads**: the dialog pre-flights with the estimate (an expired session goes to sign-in,
  a refusal is a sentence), then posts into a fresh hidden frame; if the frame loads the
  server's JSON error instead of a file, the status line says so.
- **Counts** (header, scrubber, filter facets) reload after trash, hide, restore, date fixes
  and uploads (`library.version`). Facets load only while the filter panel is shown, after the
  first thumbnails; years and sources are counted without their own filter, so other values
  stay listed and a chosen value with no matches can be unticked.
- **Theme**: dark by default; Settings offers Light and Like the system.

## Performance (library grid, 10 000-photo mock, phone 390×844, CPU ×4)

Measured with `e2e/perf.spec.ts` (instructions at its top) on a production build, median of
three runs (before = integrate/m2 web, after = this branch). Main-thread time from a
DevTools trace of the same 30-screen scroll.

| | before | after |
|---|---|---|
| Time to first decoded thumbnail | 1.66 s | 1.30 s |
| `/api/assets` pages fetched on first load | 2 | 1 |
| DOM nodes at the top of the library | 465 | 274 |
| Scroll 30 screens (360 frames) | 23.7 s | 16.5 s |
| Long tasks while scrolling down (loading as it goes) | 5 | 1 |
| Long tasks scrolling back up (all loaded) | 4 | 5 |
| Main-thread busy during the scroll | 22.6 s | 17.1 s |

What changed: tiles render only within ±1.5 screens of the viewport (windowing inside a month,
from the justified layout boxes), and that band moves about once per half screen, not every
frame; grid offsets are measured once per layout change instead of `querySelectorAll` +
`getBoundingClientRect` on every scroll frame; the next page is fetched only when the end of
what is loaded is within a screen (the first load no longer fetches page 2 because the grid
had no width yet); month layouts are cached so a new page lays out one or two months; facets
wait for the panel and the first thumbnails. The mock's SVG images are costly to rasterise,
which dominates the remaining frame time; real WebP thumbnails are cheaper.

## Asks for the backend (beyond the contract)

- **ZIP file name** (still open after v1.2): `POST /api/downloads` always answers
  `Content-Disposition: attachment; filename="photos.zip"`. A form post into a frame cannot
  rename the file on the client. Please name it after the scope: `album_id` → `<album
  title>.zip` (same sanitising as the print PDF), `filters` → `photos-<filters in words>.zip`
  (e.g. `photos-2019-Paris.zip`), `ids` → `photos-<n>.zip`, with the RFC 6266 `filename*`
  form as for single downloads. The mock already does this.
- **Backups**: `PATCH /api/backups/{id}` accepts only `{enabled}`; to change a schedule or
  quiet window after adding a target the UI would need `{schedule?, quiet_window?,
  retention?}` there. Today the schedule is set when adding.
- **Rate-limited sign-in**: no admin endpoint exists to clear the login lock for a user, so
  the admin page has no “Unlock”. If wanted: `POST /api/users/{id}/unlock` → `204`.


- Accept the form-encoded `request` field on `POST /api/downloads` (assumption 1).
- Honour `?edit=none` on `/api/assets/{id}/preview` (assumption 3).
- Optional: `GET /api/users/directory` for album sharing by non-admins (assumption 8).
- Optional, tests only: a reset endpoint enabled by a test setting, so the E2E suite can run
  fully against the real backend.

## Not in this slice

Small multiples by place and draw-to-filter on the map are M3. Splitting a person
(`POST /api/people/split`) and face boxes in the loupe have no UI yet. Map → library opens a
place filter (there is no id or bounding-box filter); when the place holds more photos than the
dot, the map says so (“This dot holds M photos; the library … shows all N”).

## Dependencies added (dev only)

`@playwright/test` and `@axe-core/playwright` (both listed under “Web tests” in
TECH_DECISIONS). The map outline is generated once from Natural Earth 1:110m (public domain,
via the `world-atlas` npm tarball) by `scripts/make-world.ts` into `src/lib/world.ts`; icons by
`scripts/make-icons.ts`. No runtime dependencies were added; D3, MapLibre and
openapi-typescript (named in TECH_DECISIONS) turned out unnecessary for M2.
