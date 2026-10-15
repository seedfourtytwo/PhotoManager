# Flight: UI rebuild plan

Date: 2026-10-15. Brief from C: "modern, snappy and slick, as if designed by the best from Apple
and Tesla/SpaceX combined", on the web and on the phone; swiping between photos on a phone must be
smooth. Builds on the redesign specs of 2026-10-08 and 2026-10-14 and the UI direction (iPhone
glass, motion first, the partner is the audience).

The target look is [flight/design-system.md](flight/design-system.md). The screen-by-screen
reviews, each with what is wrong (file:line) and the Flight spec for laptop and phone:

- [flight/library-search-viewer.md](flight/library-search-viewer.md): Library, Calendar, Search,
  viewer chrome, Editor, dialogs, toasts, motion.
- [flight/collections-people-places.md](flight/collections-people-places.md): Collections, Albums,
  one album, print, People, one person, Places/Map.
- [flight/admin-settings-auth.md](flight/admin-settings-auth.md): You, Admin, sign-in, setup,
  To review, Trash.
- [flight/foundations.md](flight/foundations.md): tokens, font, guards and tests that must change
  on purpose, the spring helper, the shell, and the slice table this plan follows.

Reviews were made on the synthetic library at 1440×900 and 390×844; the screenshots stay on the
laptop. Home is out of these reviews: another session is building per-person Home sections, and
Home takes the Flight tokens after slice 1.

## Why it does not look slick today

Six root causes explain most of what every screen shows:

1. The page is blue-grey `#0d0f12`, not black, so photos never float.
2. "Glass" is 74 % opaque with a weak blur: it reads as a grey slab (the laptop top bar is a
   flat strip; the viewer's bar shows a seam over photos).
3. The face (Atkinson Hyperlegible) is built for low vision, not for display sizes; its slashed
   zeros show in every date.
4. Layouts are columns pinned left or capped widths (Home hero at 58 %, settings at 40 rem, places
   at 192 px cards): half of a laptop screen is empty on most pages.
5. Nothing uses springs; photos give no feedback under the finger or the pointer.
6. The viewer has one photo on screen: a swipe drags it over an empty background, then the next
   photo is cut in, still decoding (the cause of the jank C saw).

## Decisions taken

- **Flight look:** true black, one glass recipe (62 % + 24 px blur + a 0.5 px light edge), radii
  14 / 28, tiny capital eyebrow labels allowed through one `.eyebrow` class, tracking only
  through `--track-*` tokens. The rules in `docs/DESIGN_PRINCIPLES.md` that forbid this are
  rewritten in slice 0 (C allowed rewriting them).
- **Inter** (Fontsource 5.3.0, OFL-1.1, variable weight and optical size, two woff2 files, self-hosted)
  is the interface face. C delegated the choice. Recorded in `TECH_DECISIONS.md` in slice 0.
- **Light mode** keeps contrast guards: secondary text `#636366`, not Apple's `#6E6E73`
  (4.15 : 1 fails).
- **No new runtime dependency:** springs are a small `lib/spring.ts`; the map stays our offline
  SVG outline, now dark.
- **Sign-in never shows photos or faces**: anyone on the home network can open it.

## Build order

Each slice is one PR, test first, `just check` plus the e2e specs that cover it (desktop and
phone, real and mock). Slices 4–8 own separate files and can run in parallel after 3.

| # | Slice | Owns | Risk |
| --- | --- | --- | --- |
| 0 | Docs: rewrite DESIGN_PRINCIPLES §1–2 for Flight, record Inter | `docs/` | low |
| 1 | Foundation: Inter, Flight colours, tokens with old names kept as aliases, glass, `.eyebrow` | `fonts.css`, `themes.css`, `tokens.css`, `base.css`, `utilities.css`, `static/fonts`, look `apply.ts`/`app.html` | medium: every screen shifts at once |
| 2 | Spring helper, first used by sheets | `lib/spring.ts`, `sheet-drag.ts` | low |
| 3 | Shell: floating glass capsule on laptop (hides on scroll), large titles that collapse into a glass capsule | `Nav`, `+layout`, `PageHead`, `Avatar` | high: every page |
| 4 | Library: slim chips, scrubber instead of the year ruler, tile hover/press, pinch zoom levels | Library route and its components | medium |
| 5 | Viewer: 3-slot pager (in progress, its own session), then glass chrome that fades on tap and grouped Details | `Loupe`, `PhotoStage`, `PhotoBar`, `PhotoInfo`, `gesture.ts` | high |
| 6 | Sheets and controls: dialogs as glass sheets, menus as glass, switches and segmented controls | `Dialog`, `Menu`, `ui/*`, `buttons.css`, `fields.css` | medium; before 7–8 |
| 7 | Collections family: full-width card grids, on-photo heroes for album and person, People grid, dark map | collections, albums, people, map, search routes | medium |
| 8 | You / Admin / sign-in / To review / Trash: two-pane settings on laptop, iOS lists on phone, plain-language errors, one PIN keypad | those routes, `components/admin`, `PinPad` | low–medium |
| 9 | Cleanup: drop the old size aliases | `tokens.css` | low |

The laptop shell (capsule on top or Mac-style sidebar) is chosen on the Superdesign canvas
before slice 3.

## Bugs found on the way (fix in the slice that owns the file)

- Change PIN never asks for the new PIN twice (slice 8).
- Trash focuses the first photo on load, so it looks selected (slice 8).
- Download → More options leaves both sizes unchecked (slice 6).
- Fix date says "Read as month first: 25 July 2019" for 25/07 (slice 6).
- Search on laptop shows two search fields (slice 7).
- The grid's default gap is 3 px in the look's `apply.ts` and 2 px in CSS (slice 1).

## Waiting on C (hard stops: schema, API contract or new dependency)

None block slices 0–9; each has a fallback that is in the specs.

| Want | Needs | Fallback |
| --- | --- | --- |
| Atkinson as a "Larger text" choice per account | a look-sheet field (backend + contract) | Atkinson leaves the default look; text dial still works |
| Blur-up placeholders in grids | a thumbhash or colour per asset (schema) | flat fill + fade-in |
| Sharp album and person heroes | album cover at preview size in `AlbumSummary` | 640 px thumb |
| Places grid without 17 requests | `GET /api/places` with covers | current requests |
| Plain-language backup errors | an `error_kind` from the server | a generic headline + raw text behind "Details" |
| One Settings for You and Admin | product call (and the Home-sections work lives in You today) | keep two pages, both restyled |
| Street-level map | MapLibre + self-hosted tiles (new dependency) | offline outline map |
