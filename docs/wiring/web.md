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
pnpm screenshots     # writes docs/screenshots/{desktop,phone}-*.png from the mock
```

In containers set `PW_CHROMIUM=/opt/pw-browsers/chromium` (both Vitest browser mode and
Playwright pass it as `executablePath`). `pnpm e2e` starts the mock on :8431 and a dev server on
:5183 itself, runs with one worker, and resets the mock (`POST /__mock/reset`) before each test.

### Running the E2E suite against the real backend

```sh
# backend running with a fresh, empty data dir, web built and served on :8420
E2E_BASE_URL=http://127.0.0.1:8420 E2E_MOCK_URL= pnpm e2e
```

With `E2E_MOCK_URL` empty, tests that need a known state (`resetMock`) are skipped; set
`E2E_USER`/`E2E_PASSWORD` for the admin. To run the full suite against the backend, the backend
needs an equivalent test-only reset (see “Asks” below) — or point `E2E_MOCK_URL` at it if it
implements `POST /__mock/reset`.

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

## Asks for the backend (beyond the contract)

- Accept the form-encoded `request` field on `POST /api/downloads` (assumption 1).
- Honour `?edit=none` on `/api/assets/{id}/preview` (assumption 3).
- Optional: `GET /api/users/directory` for album sharing by non-admins (assumption 8).
- Optional, tests only: a reset endpoint enabled by a test setting, so the E2E suite can run
  fully against the real backend.

## Not in this slice

Hand-picked upload (FEATURES 10.2) has no route in contract v1 and is not built. People,
small multiples by place, and draw-to-filter on the map are M3.

## Dependencies added (dev only)

`@playwright/test` and `@axe-core/playwright` (both listed under “Web tests” in
TECH_DECISIONS). The map outline is generated once from Natural Earth 1:110m (public domain,
via the `world-atlas` npm tarball) by `scripts/make-world.ts` into `src/lib/world.ts`; icons by
`scripts/make-icons.ts`. No runtime dependencies were added; D3, MapLibre and
openapi-typescript (named in TECH_DECISIONS) turned out unnecessary for M2.
