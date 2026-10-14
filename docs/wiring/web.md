# Web app wiring (M2)

> **Part reference, part record.** This page began as the integration record of the M2 web
> branch. Four sections are still edited when the app changes: "Run it", "Tests", "The mock
> API" and "Screens and behaviour". The others ("Contract assumptions", "Performance", "Asks
> for the backend", "Not in this slice", "Dependencies added") record that branch as it was
> merged: names, numbers and open asks in them may be stale. For the settings see
> [`docs/guides/settings.md`](../guides/settings.md); for how the app is built today see
> [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).

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
pnpm mock            # mock API on http://127.0.0.1:8421, sign in as C with PIN 1234
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
route in the contract in memory: sessions and cookie, 401/403/404 rules, the wait and the
lock after wrong PINs (`/__mock/reset` with `locked: <user name>` starts with a locked account),
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
  the grid to that photo and focuses its tile). On a phone the Info sheet is a history entry
  of its own over the photo's, marked `page.state.info`, and the sheet is open exactly while
  the current entry has the mark: Back closes it, its own button goes back, and stepping
  rewrites that entry and adds none. The photo's own entry under it then names an earlier
  photo; when Back arrives there, the photo on screen is held and written into it. Chrome fades after 2.5 s and returns on any
  touch, key or mouse movement; a tap on the photo toggles it (after 300 ms, in case it is
  the first half of a double tap, which zooms). The photo area has `touch-action: none`,
  so vertical swipes (up = info, down = close) and two fingers are not taken by the browser;
  `lib/gesture.ts` says what each press means, `lib/zoom.ts` how large the photo is and where
  it sits (double tap, two fingers, one finger on a zoomed photo; the Zoom pill and Z do what
  a double tap does). Favourite/Private are optimistic and single-flight. View-only
  photos show a disabled Download with the reason; Edit/Fix date/Private need `edit` (contract
  v1.2); Private, Fix date and More like this sit behind More. Opening and closing run through
  `withTransition` (`lib/motion.ts`); the page takes no input while a view transition runs.
- **Time ruler** (`TimeRuler`, `lib/ruler.ts`): linear in time, from the newest month with
  photos to the oldest (`GET /api/calendar`). It jumps once, where a drag ends.
- **Grid**: one Tab stop; arrow keys, Home/End move between photos across months.
- **Search** (`/search?q=…`, `/search?like=<id>`), **People** (`/people`, `/people/<id>`: rename, hide,
  merge, change portrait), **Print** (`/albums/<id>/print`), **Admin → Backups / Cloud folders / Search and
  faces**, **Settings → Phones and devices**.
- **Portraits** (`Portrait`, `PortraitDialog`, `lib/portrait.ts`): a person's round picture is
  an `<img>` of `Person.portrait.url`, which the server cuts; the address changes with the
  picture, so a saved change shows at once. "Change portrait" (members and admins; the
  portrait itself is the same button) lists `GET /api/people/<id>/faces`, shows the picked
  photo without its edits (`/api/assets/<id>/preview?edit=none`) under a round window, and
  moves and zooms it by drag, pinch, wheel, slider and keys (arrows, + and -). The circle
  cannot leave the photo. Save is `PUT /api/people/<id>/portrait`, "Use automatic" `DELETE`.
- **Collections** (`/collections`, `CollectionRows`): each row of the account's look shows what
  is behind it and asks only for that: People `GET /api/people`, Albums `GET /api/albums`,
  Places `GET /api/assets/facets` and then `GET /api/assets?place=<name>&limit=1` for each of
  the sixteen biggest places (its newest photo is the cover, and tells a country from a city).
  A row that fails says so in the toast and the others stay. The ordering rules are pure, in
  `lib/collections.ts`.
- **Navigation**: the places of `PLACES` (`lib/nav.ts`: Library, Collections) and Search, in a
  top bar on a laptop and a floating dock on a phone; the avatar opens You (`/settings`: look,
  Needs you and Admin for admins, phones, Change PIN, Sign out). There is no account menu: To
  review and Trash are reached from Collections. A page change is a view transition of the page
  area (`onNavigate` in the root layout, `pageMove` decides the direction, `movePage` in
  `lib/motion.ts` runs it). The selection pill shows Add to album, Download,
  Fix date and Move to trash (the first three on a phone) and puts the rest under “More”.
- **Date fields** (`DateField`, the reader in `lib/dates.ts`): Fix date's “Set exactly” and
  the filters' From / To are one text field, never the browser's own date control, so the
  date is shown day first on the 24-hour clock whatever the browser's language
  (`04/07/2019 18:30:05`; a filter shows the day only). `readDateText` reads what is pasted or
  typed: the app's own displays, ISO, camera and file-name styles, numbers day first, month
  names in English and French, AM/PM. A readable paste replaces the whole field at once;
  typed text is read at every keystroke (the before → after preview follows) and tidied on
  Enter or on leaving the field. A day alone keeps the field's time and a time alone its day.
  Numbers that can only be month first (`7/25/2019`) are converted and a quiet line says so.
  Text that is not a date, or names a day or time that does not exist, gives no value: a
  sentence under the field says so, “Change date” stays disabled and the filter is left as
  it was. The API still gets `YYYY-MM-DDTHH:MM:SS`, and the URL `from` / `to` as `YYYY-MM-DD`.
- **Downloads**: the dialog pre-flights with the estimate (an expired session goes to sign-in,
  a refusal is a sentence), then posts into a fresh hidden frame; if the frame loads the
  server's JSON error instead of a file, the status line says so.
- **Counts** (header, time ruler, filter facets) reload after trash, hide, restore, date fixes
  and uploads (`library.version`). Facets load only while the filter panel is shown, after the
  first thumbnails; years and sources are counted without their own filter, so other values
  stay listed and a chosen value with no matches can be unticked.
- **Look**: each account has a look sheet (theme, mode, dials, switches; contract v1.5,
  `docs/adr/0001`). `web/src/lib/look/` holds it and imports nothing from the app: `sheet.ts`
  (the rules, mirrored from `domain/look.py`), `apply.ts` (root attributes and CSS
  variables, and what each theme itself gives the dials), `cache.ts` (`pa.look` in
  localStorage: the sheet with the id of the account it belongs to), `look.svelte.ts` (the
  account's sheet and a trial sheet, and which answer counts when requests cross: the rule
  is at the top of that file). `app.svelte.ts` fetches it after sign-in and when the tab
  comes back; a small script in `app.html` paints the cached sheet before the app loads.
  Signing out or losing the session clears the cache and shows the defaults, and a look
  cached for another account is dropped at sign-in: on a shared device nobody gets the last
  person's look. A sheet that was stored, cached or received is read field by field, so one
  field this build cannot read (or does not know) costs only itself. Dark by default;
  Settings offers the mode (Dark, Light, Like the device), saved on the account.
  The earlier per-browser `pa.theme` key becomes the mode of an account that still has the
  defaults, once; for an account that already has a look it is only removed.
  The size of the photos in the grids is the look's `thumbSize` and nothing else: the earlier
  per-browser `pa.density` key (a Settings choice that is gone) is removed when the app loads.

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
- **Rate-limited sign-in**: answered since. `POST /api/users/{id}/unlock` → `204` clears the
  lock, and Admin → People shows “Unlock” on a locked account (`admin/Users.svelte`).


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
via the `world-atlas` npm tarball) by `scripts/make-world.ts` into `src/lib/world.ts`; the
PWA icons in `static/` by `scripts/make-icons.ts` (the interface's own icons are drawn in
`src/lib/icons.ts`). No runtime dependencies were added; D3, MapLibre and
openapi-typescript (named in TECH_DECISIONS) turned out unnecessary for M2.
