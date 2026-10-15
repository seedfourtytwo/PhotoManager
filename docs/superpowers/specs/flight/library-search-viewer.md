# Flight review: Library · Calendar · Search · Viewer chrome · Editor · Dialogs

2026-10-15. Target: `../design-system.md` ("Flight"). Inputs: every screenshot in `review/` and
`review/raw/` for these screens (desktop 1440x900, phone 390x844), plus the components.
Out of scope: viewer paging (PhotoStage/Loupe swipe/gesture.ts/loupe.svelte.ts), which another
session is rewriting. Paths are relative to `web/src/lib/` unless they start with `routes/`.

Severity: **P0** breaks the Flight bar or looks broken · **P1** clearly below the bar · **P2** polish.
**[API]** = needs a backend/API change (each one is listed again at the end).

---

## 0. Global gaps, the root cause of most findings

| # | Now | file:line | Flight |
|---|---|---|---|
| G1 P0 | Page is `#0d0f12` blue-grey, not black; sheets `#171a1f` | themes.css:13-14 | `--bg #000`, `--raised #111214`, `--fill #1C1D20` |
| G2 P0 | "Glass" is 74% opaque `--raised` + `blur(18px) saturate(1.4)`; reads as a grey slab, no edge highlight | tokens.css:18, :66; utilities.css:49-65 | `rgb(22 22 24/.62)` + `blur(24px) saturate(1.8)` + `--glass-edge` inset 0.5px highlight |
| G3 P0 | Face is Atkinson Hyperlegible with slashed zeros ("2Ø26", "Ø9:Ø1") everywhere data shows | tokens.css:22-26 | Inter / Inter Display, `font-variant-numeric: tabular-nums`, no slashed zero; Atkinson kept for "Larger text" only |
| G4 P1 | Radii 12/20 px; Flight wants 14 / 28 | tokens.css:53-54 | `--r-1 14px`, `--r-2 28px` (sheets, cards, menus) |
| G5 P1 | Menus, sheets, toasts, popovers all solid `--raised`; nothing floats as glass | Menu.svelte:147-160, SelectionBar.svelte:207-218, FacetSheet.svelte:84-98, +layout.svelte:227-247 | One `Surface` primitive: `glass` (bars, pills, menus, toasts) or `raised` (long sheets) |
| G6 P1 | Motion is CSS easing only; no spring anywhere, no press feedback on photos | tokens.css:87-92 | Add `spring.ts` (stiffness 340, damping 30, mass 1, seeded with release velocity) for gestural things; keep the two curves for fades and sheets |

---

## 1. Library (grid, header, chips, ruler)

### What is wrong, ranked
| # | Issue | file:line |
|---|---|---|
| L1 P0 | **Time ruler** on laptop is a debug scale: 14 year labels + ticks in a 60 px column, always visible, eating 64 px of grid width; the "Sep 2026" accent badge sits *on* the toolbar row and collides with the Upload icon | TimeRuler.svelte:253-294; routes/+page.svelte:241-249 (column), :236-238 (grid padding-right 64 px) |
| L2 P0 | **Phone ruler** is a horizontal glass strip pinned above the dock, a third floating layer (dock + ruler + toasts/pill). Unlike anything in iOS; covers a row of photos | TimeRuler.svelte:297-305; routes/+page.svelte:257-266 |
| L3 P0 | **Phone header** crams segmented + Select + Upload + avatar beside a 34 px title; avatar duplicated (the dock has none, the header has one) | LibraryHead.svelte:30-41, :53-60; PageHead |
| L4 P1 | **Sticky month headings** are solid `--bg` strips (`background: var(--bg)`), so a hard band cuts the photos as they scroll under; on phone they stack below the compact title as a second strip | Timeline.svelte:271-280, :293-303 |
| L5 P1 | **Compact phone title** is full-width; the screenshot shows a darker rectangle behind the word (seam), not a capsule | PageHead.svelte:113-136; raw/phone-03b-library-ruler.png |
| L6 P1 | **Chips are heavy**: 40 px, 16 px/600 text, 24 px icons, `--fill` solid; on phone the row clips "Fa…" with no fade edge; set chip turns into a white slab with a separate × half | buttons.css:154-176; Chip.svelte:45-62; FilterChips.svelte:188-194 |
| L7 P1 | **Tiles have no hover/press/load state**: hover sets the same background it already has; no press scale; no fade-in, image pops in over a `--hairline` grey box | PhotoGrid.svelte:241-258, :265-271 |
| L8 P1 | **Selection** is a 3 px amber frame + 22 px check; unselected tiles show nothing while choosing (no empty circles), so on a phone "am I selecting?" is unclear | PhotoGrid.svelte:276-312 |
| L9 P1 | **Gutters** look ~4 px (gap from look settings) vs Flight 2 px | Timeline.svelte:54; tokens.css:59 |
| L10 P2 | Loading/empty: "Loading…" plain text at the bottom; empty library is two paragraphs | Timeline.svelte:242-249; routes/+page.svelte:~145-156 |
| L11 P2 | Only 3 fixed sizes (small/medium/large in Settings); no pinch, no ⌘+/− | timeline.ts:114-117 |
| L12 P2 | Lasso is a 2 px accent rectangle with 8% fill; OK, but on a black page reads as an error box | Timeline.svelte:284-290 |

### Flight spec

**Header (both):** iOS large title. `Library` 34/700 at rest, count under it in 13/500 `--ink-2`
("12,480 photos · 2012–2026"). On scroll the large title translates up and fades
(scroll-driven, `animation-timeline: view()`; fallback IntersectionObserver as now) while a
**glass capsule** title (15/600) fades in at the top centre. No solid strip anywhere.

| | Laptop | Phone |
|---|---|---|
| Title row | Title left; right side a single glass cluster: `[Grid | Days]` segmented (32 px), Select, Upload as 36 px glass circles | Title left; right: **Select** as a text pill (15/600, glass) and a `⋯` glass circle (Upload, Calendar view, Grid size). Avatar leaves the Library header (lives in the dock/You) |
| Compact bar | Laptop top-bar is already glass (Nav); month label becomes the bar's subtitle | 44 px glass capsule, 16 px from edges, `Library` + current month ("Sep 2026") in 13 px under it — replaces sticky month strips |
| Month headings | Not sticky. 22/650, 24 px above, 8 px below; on scroll the current month shows in the top bar | Same, 17/650, with the count right-aligned 13 px `--ink-2` |

**Chips (both):** 32 px visual (44 px hit via `::before` inset −6 px), 15/500, 16 px icons,
glass on photos / `--fill` on black, 8 px gap. Set chip = ink fill, black text, the × inside the
same pill (one shape, 6 px gap). Row: horizontal scroll with 24 px mask-fade at the right edge,
`scroll-snap-type: x proximity`. Laptop: chips sit on the same row as the title cluster when
≥1280 px (saves 56 px). Answered count > 0 → a `Clear` text chip at the end (already exists).

**Grid:** 2 px gutters (Flight default; the look's gap dial can still widen). Black behind.
- **Load:** tile shows a flat colour placeholder, image fades in 180 ms `opacity` once `decode()`
  resolves. **[API] A1** for a real blur-up (thumbhash/dominant colour); without it, use
  `--fill` and the fade (no shimmer on photo grids: shimmer on 300 tiles is noise).
- **Hover (laptop):** image `scale(1.03)` inside the clipped tile 240 ms `--ease`; empty check
  circle fades in top-left; tiny date chip bottom-left fades in (13 px on scrim).
- **Press:** `scale(0.97)` 100 ms, release springs back. Long-press (phone) = Apple's context
  preview: tile lifts (scale 1.04, `--lift` shadow), glass menu with icons
  (Favourite, Share, Add to album, Select, Hide, Delete) — reuses `ActionMenu`.
- **Selecting:** every tile shows an empty 24 px white-ring circle bottom-right (iOS place);
  selected = filled accent circle + check, tile `scale(0.92)` with 0 radius kept, 120 ms spring;
  no frame. Header title becomes "3 Selected" (large title cross-fades), Select becomes Done.
- **Zoom levels:** 5 steps per device. Phone row heights 60 / 84 / 110 / 160 / 240 px
  (60 = "years" density, Apple 9-across feel), laptop 120 / 160 / 220 / 300 / 420. Pinch
  (two-pointer distance ratio, threshold 1.15/0.87) or ⌘+/⌘−/ctrl-wheel steps one level.
  Transition: anchor the tile under the pinch centre; FLIP — snapshot boxes, relayout, animate
  `transform` from old box to new, 320 ms spring; tiles entering fade in. Persist level per device
  (localStorage). Thumbs are 640 px long edge (backend derivatives.py:18): enough up to 320 CSS px
  at 2x; the 420 px laptop step asks the 2048 preview for the visible tiles only.
- **Lasso (laptop):** 1 px `--ink` 40% border, `--ink` 6% fill, 6 px radius; selected tiles
  animate as above during the drag.

**Time ruler → scrubber (both):** hidden at rest. Appears (opacity 0→1, 160 ms) on scroll
velocity > 1.5 screens/s or when a finger/pointer enters the right 32 px edge; hides 1.2 s after
idle (keep `Idle`).
- Visual: a 6 px-wide glass thumb (44 px tall hit area) riding the right edge, no ticks, no
  year column. While dragging: thumb grows to a glass pill with "September 2026" 15/600 and
  a faint year list fades in at 50% opacity along the edge (only years, 13 px, spaced by
  data). Haptic tick (`navigator.vibrate(5)`) per year crossed on Android; nothing on iOS.
- Phone: same vertical scrubber (not a horizontal strip); it sits above the dock's top edge and
  below the compact bar. The selection pill no longer has to replace it.
- Keep: slider role, keyboard steps, `monthAt`/`position` maths, jump-on-release.

**Empty / loading:** first load = 3 rows of `--fill` blocks in justified shapes with a single
slow shimmer sweep (1.6 s, 6% white, `transform` on a gradient overlay) — only before the first
page arrives. Paging = nothing visible (prefetch earlier: 2 screens, not 1). Empty library = a
centred glass card: icon, "No photos yet" 22/650, one line, `Upload` primary + "Add a folder"
(admin) secondary.

---

## 2. Selection pill + its More menu

| # | Issue | file:line |
|---|---|---|
| S1 P0 | Phone: pill floats above the dock = two stacked capsules + ruler slot; pill clips under the dock edge | SelectionBar.svelte:227-231; raw/phone-06-selection.png |
| S2 P1 | More menu: plain text list, no icons, solid panel, opens from the right edge over photos; "Select loaded (200)" exposes paging | SelectionBar.svelte:158-168, :207-226; selection.ts:78-80 |
| S3 P1 | Count "3" in accent is the only accent use outside frames; icons without labels on laptop (Add/Download/Delete look identical in weight; Delete not red) | SelectionBar.svelte:190-196, :128-142 |
| S4 P2 | No enter/exit motion; pill pops | SelectionBar.svelte:173-189 |

**Flight:**
- **Phone:** while selecting, the **dock morphs into the selection bar** (same capsule, same
  place, 64 px): `Share · Add to · Delete · ⋯` icon-over-word, and the count lives in the large
  title ("3 Selected"). Morph = cross-fade contents 160 ms + width spring. The search circle
  beside the dock becomes `Done`.
- **Laptop:** glass capsule bottom-centre, 52 px: `✕  3 selected | Share  Add to  Download  Favourite | Delete  ⋯`
  with words beside icons (15/500) at ≥1280 px; Delete in `--fail` tint. Rises 24 px + fades,
  380 ms sheet curve; leaves the same way.
- **More menu → `ActionMenu`** (shared): glass, 28 px radius, rows 44 px with leading 20 px icon,
  grouped with 8 px gaps (not lines): [Fix date, Favourite, Pin to Home] [Hide, Make private].
  Opens with scale 0.9→1 + fade from its anchor corner, 220 ms spring (Apple context menu).
  Phone: same menu, anchored above the bar.
- "Select all" for an unloaded library: label just "Select all"; **[API] A2** to act on a
  filter scope instead of ids.

---

## 3. Filter sheets / popovers (FacetSheet + Who/When/Where/Camera/More)

| # | Issue | file:line |
|---|---|---|
| F1 P1 | Laptop popover: solid `--raised`, no scrim, sits over photos with no separation, 24 rem wide, scrolls internally (month grid cut at the bottom) | FacetSheet.svelte:84-117; raw/desktop-05-filters.png |
| F2 P1 | When: 13 identical year bars, all grey, selected year white; months grid with disabled ghosts ("Feb" at 20% ink) | WhenQuestion.svelte, YearBars.svelte |
| F3 P1 | Phone sheet: 88dvh, 92 px row rhythm, "Clear / Done" small text top-right, no detents | FacetSheet.svelte:164-205 |
| F4 P2 | No live result count; you pick, close, then see what you got | FilterChips.svelte:90-101 |

**Flight:**
- **Laptop:** glass popover (`ActionMenu` surface), 360 px, max 70vh, anchored under the chip with
  a 12 px gap, scale-from-chip 220 ms spring. No inner scroll for When: years as a 4-col grid of
  tabular year tiles (year 17/600 + count 13 `--ink-2`, bar as a 3 px underline proportional to
  count); months appear inline under the chosen year as a 6x2 grid; months with 0 photos are
  simply absent.
- **Phone:** `Sheet` with two detents (medium 55%, large 92%), grab handle, title left 22/650,
  `Done` as a glass pill right. Results line pinned at the sheet bottom: "Show 28 photos" primary
  button (count from `/api/facets` already used by the chips — verify it returns totals for the
  pending filter; if not, **[API] A3**).
- Where/Camera/Who: rows → chips/tiles (faces as 56 px circles for Who, places as text chips).

---

## 4. Calendar (Library → Days view)

| # | Issue | file:line |
|---|---|---|
| C1 P0 | It is a GitHub contribution heatmap: grey squares, no photos. Not Apple Photos, not "content first" | CalendarHeatmap.svelte:22-60 |
| C2 P0 | Phone: SVG min-width 40 rem forces a sideways scroll; Aug–Dec are cut off with no affordance | CalendarHeatmap.svelte:91 |
| C3 P1 | Laptop: capped at 60 rem → right 40% of the screen empty; legend paragraph under it | CalendarHeatmap.svelte:72, :62-67 |
| C4 P2 | Empty years (2023 "0") drawn as full grids of empties | CalendarHeatmap.svelte:24-59 |

**Flight — replace with Apple's Years / Months mosaic** (the segmented becomes `Years | Months | All`):
- **Years:** one full-bleed card per year (laptop: 2 per row 16:9; phone: 1 per row 4:5), cover
  photo, scrim, big tabular year bottom-left 40/700 ("2019"), count + top places 13 px. Tap →
  Months scrolled to that year. Data: `/api/home` `years` already gives a cover per year (types.ts:311-317) — no API change.
- **Months:** per year a header, then month cards (laptop 4-up 3:2, phone 2-up 1:1), cover +
  "July" 17/650 + count on scrim. Tap → All, jumped to that month. Needs a cover per month:
  **[API] A4** (`/api/calendar?by=month` → `{month, count, cover}`), or N calls to
  `/api/assets?year&month&limit=1` as a stop-gap.
- Keep the day heatmap only as a compact strip inside the When filter (useful there).
- Cards: press 0.97, hover image scale 1.03; enter as staggered fade-up 40 ms apart, max 8.

---

## 5. Search (empty, results, "meaning")

| # | Issue | file:line |
|---|---|---|
| Q1 P0 | Laptop shows **two search fields** (top bar + page) | routes/search/+page.svelte:105-117; Nav.svelte |
| Q2 P0 | Field auto-focuses with a 2 px **orange ring** on every visit: reads as an error; the accent is for selection | routes/search/+page.svelte:191-193, :33 |
| Q3 P1 | Admin disclaimer paragraph sits at the top for everyone (even if worded softer for members) | :119-125 |
| Q4 P1 | Meta line "200 photos, ranked by meaning" + a stray phone icon (Keep on phone) with no label; 200 is the request cap, not the real count | :140-145, :64 |
| Q5 P1 | Submit-only search; "Searching…" plain text; results are an undifferentiated justified grid (score unused) | :85-89, :137-138, :152 |
| Q6 P1 | Empty state: People circles + place chips left-packed; nothing for things, years, recents; desktop has huge dead space | SearchSuggestions.svelte |
| Q7 P2 | Phone: dock's search circle shows no active state on /search | Nav.svelte |

**Flight:**
- **One field.** Laptop: the top bar's search circle expands into the field (design-system top
  bar), and `/search` uses that field; the page has no second field. Phone: field at the top of
  the page, 44 px glass capsule, `Cancel` text button slides in when focused (iOS). Focus = ring
  in `--ink` 30%, never accent.
- **Typing:** debounce 250 ms, live results; keep URL `?q=` in `replaceState`. Suggestion rows
  appear under the field while typing (person / place / album / year matches, with leading
  thumbnail or face) — client-side from data already loaded (people, places, albums).
- **Empty state (both):** sections as rails, full width: *Recent* (localStorage, chips,
  clear-all), *People* (72 px faces, horizontal rail), *Places* (3:2 cover cards, needs a cover
  per place: the map/facets data has counts; cover **[API] A5** optional, fallback chip list),
  *Things* (only when semantic ready: "Beach", "Snow", "Birthday"… as glass chips over a sample
  photo), *Years* rail (reuses Years cards).
- **Results:** header line 13 px `--ink-2` "Top results" then a 2-row hero band of the best
  scores at large tile size (score from `ScoredAsset.score`, types.ts:388), then "All results"
  justified grid. Count: "Showing 200 most alike" when capped, real count otherwise
  (**[API] A6** to page/count semantic results). Keep-on-phone moves into a `⋯` menu in the header.
- **Not set up:** one quiet line at the very bottom of results for admins only ("Search by what
  is in a photo: set up in Admin"); members never see it.
- **Loading:** grid skeleton (justified grey blocks, one shimmer) after 150 ms; under 150 ms show
  nothing (no flash).

---

## 6. Viewer chrome (bars, Details, More, zoom)

| # | Issue | file:line |
|---|---|---|
| V1 P0 | Bottom bar is a 2-line readout card (date + EXIF) + icon row, 360 px wide floating over the photo's bottom third; on laptop it overlaps the photo with a visible seam/gradient band | PhotoBar.svelte:111-122, :173-234; raw/desktop-04-loupe.png |
| V2 P0 | Phone: photo is off-centre — 130 px empty band on top, bar covers the bottom; chrome is opaque cards, not glass over a black stage | Loupe.svelte:338-358; raw/phone-04-loupe.png |
| V3 P0 | Laptop Details open by default as a short striped table in a 336 px column, with a keyboard-hint line and ~50% empty column below | Loupe.svelte:325-327; PhotoInfo.svelte:165-171, :176-182, :248-254 |
| V4 P1 | Details content: label/value table ("Taken / Place / Camera / Settings / From"), file paths and "2026-09-07 09.01" filename noise up front; no map, no people faces up top | PhotoInfo.svelte:60-150 |
| V5 P1 | Phone Details sheet covers the photo (50dvh, fixed), the photo does not move up; sheet is solid | PhotoInfo.svelte:255-294 |
| V6 P1 | Prev/next chevrons drawn on phone (grey `<` `>` mid-photo) | PhotoEdges.svelte:73-84 |
| V7 P1 | More menu: 3 text rows, no icons, solid panel overlapping the bar's readout | PhotoBar.svelte:163-165; Menu.svelte:147-176 |
| V8 P1 | Zoom: icon button toggles 1x/2x; no level readout, no double-tap point zoom feedback, chrome vanishes with no way back but tapping; photo slides under the top buttons | Loupe.svelte:195-201, :262-268; raw/*-04d-loupe-zoom.png |
| V9 P2 | Top-right cluster: zoom + fullscreen + info as three separate circles; Close is a chevron-down | Loupe.svelte:249-285 |

**Flight:**
- **Stage:** true black, photo `contain`, centred in the full viewport (chrome overlays, never
  reserves space). Safe-area aware.
- **Top bar (glass, fades):** phone — left glass circle `‹` (back to grid), centre two-line title
  "7 September 2026" 15/600 + "09:01 · Carnac" 13 `--ink-2`, right glass circle `⋯`. Laptop — same
  in a centred glass capsule, plus `Info` and `Zoom %` on the right.
- **Bottom bar (glass, fades):** phone — 5 icons evenly spaced in a 56 px glass capsule:
  Share/Download · Favourite · Info · Edit · Delete (trash). No text readout (the date is on top).
  Laptop — same capsule, 400 px, centred, 24 px from the bottom.
- **Fade on tap:** single tap toggles chrome (opacity 200 ms `--ease`; background stays black).
  Auto-hide after 3 s idle on laptop only (mouse). Keep current Idle + double-tap delay.
- **Filmstrip (laptop, P2):** a 48 px strip of neighbours at the very bottom under the bar,
  fades with the chrome; current tile wider (Apple Photos iOS 17 scrubber). Phone: on drag-up
  past 24 px, Details opens instead.
- **Details:**
  - Phone: **swipe up** (or Info) slides the photo up to the top 40% (transform, spring 340/30)
    and a sheet rises under it (not over it): grouped cards, 28 px radius, `--raised`.
  - Laptop: right panel 360 px, glass over the black, slides in (translateX 24px + fade, 280 ms);
    **closed by default**, I toggles, the stage re-centres with a spring.
  - Card order: (1) **Title card** — date 22/650 + time/timezone 13; place line; "Add a caption"
    **[API] A7** optional. (2) **People** — face rail 44 px. (3) **Map card** — mini map from
    the offline `world.ts` land path, a dot at lat/lon, place name on it, 16:9, tap → /map
    focused there. **No online tiles** (AGENTS.md: metadata never leaves the machine); detailed
    street-level map needs offline tiles **[API] A8**. (4) **Camera card** — "iPhone 15" 15/600,
    lens/focal, then a 4-cell spec row ISO · mm · f/ · s in tabular 15/600 with 11-caps labels
    (the SpaceX touch). (5) **Albums** chips. (6) **File** — collapsed "File info" row:
    name, 4000 x 6000 · 6.3 MB, sources/paths (admins only), date source.
  - Keyboard hints move into a `?` popover (laptop), never in the panel.
- **More (`⋯`) → `ActionMenu`** with icons: Add to album, Fix date, Pin to Home, Private,
  Hide, Copy, Download options…; anchored to `⋯`, opens downward from the top bar.
- **Zoom UI:** double-tap zooms to 2.5x at the tap point (spring); pinch anywhere; laptop scroll
  wheel/trackpad pinch. A small glass pill "2.5×" top-centre appears for 1 s on change; tapping
  it returns to fit. Zoomed: chrome hidden but a 1-finger tap brings it back (already). Laptop
  zoom button shows the % and cycles Fit → 100% (pixel 1:1) → 200%.
- **Open/close:** keep the shared-element view transition (tile ↔ photo); during it the chrome
  fades in 120 ms after the photo lands. Swipe-down dismiss: background opacity follows the
  drag, chrome hides immediately (pager session owns the gesture; this only styles it).

---

## 7. Editor

| # | Issue | file:line |
|---|---|---|
| E1 P0 | Toolbar is a wrapped row of plain text buttons ("Rotate left / Rotate right / Flip horizontal / Flip vertical") — wraps to two lines on phone | Editor.svelte:207-216, :380-395 |
| E2 P1 | Save/Cancel/Reset at the bottom right, Save a white pill; phone leaves 300 px of dead space above the photo | Editor.svelte:241-259; raw/phone-13-editor.png |
| E3 P1 | Crop: corner handles only, no edge handles, no rule-of-thirds grid while dragging, no auto-recentre/zoom after a drag | Editor.svelte:177-201, :317-378 |
| E4 P1 | Straighten is a stock range input with "0°" label | Editor.svelte:224-234 |
| E5 P2 | Only geometry; no light/colour adjustments | **[API] A9** (recipe + renderer) |

**Flight (Apple Photos edit layout):**
- **Top (glass, safe-area):** `Cancel` left (text), title "Crop" centre 15/600, `Done` right as
  an accent-free ink pill. Reset appears as a small glass pill under the top bar only when changed.
- **Stage:** photo centred in the remaining height, 16 px side margin; crop frame 1 px white 80%,
  L-shaped 3 px corner marks 20 px long, plus edge midpoint bars; thirds grid fades in (30%
  white, 0.5 px) while dragging; outside dimmed 55%. On release the crop animates back to centre
  and fills the stage (320 ms spring).
- **Bottom toolbar (glass capsule):** icon buttons with words under (11 px): Rotate ⟲, Flip ⇋,
  Aspect ⧉ (opens a chip row: Free · Original · Square · 4:5 · 3:2 · 16:9, plus portrait/landscape
  toggle), Straighten. Straighten = **horizontal dial**: tick ruler that scrolls under a fixed
  centre needle, value in tabular 13 px above, haptic-like snap at 0°.
- **Mode tabs (future):** `Adjust · Filters · Crop` segmented above the toolbar when A9 lands;
  until then Crop only, no tabs.
- Phone: same, toolbar 64 px above the home bar; laptop: toolbar centred 560 px.
- Revert-to-original moves into a `⋯` in the top bar.

---

## 8. Dialogs → sheets (Dialog, DownloadDialog, FixDateDialog, AddToAlbum…)

| # | Issue | file:line |
|---|---|---|
| D1 P0 | Laptop dialogs are centred cards with native radio buttons, checkboxes, `<select>` and number spinners (FixDate) — browser-default look | DownloadDialog.svelte:190-310; FixDateDialog.svelte:82-95 |
| D2 P1 | Download "More options" reveals 4 groups of raw radios; while open, **neither Full size nor Smaller is checked** (state looks broken) | DownloadDialog.svelte:190-226; raw/*-07b-download-more.png |
| D3 P1 | Action row: `Cancel` text + white primary pill bottom-right on laptop and phone; on phone not full-width | Dialog.svelte:35-38, :75-81, :120-122 |
| D4 P1 | Fix date copy bug: "25/07/2019" shows "Read as month first: 25 July 2019" (25 cannot be a month; the note contradicts itself) | DateField.svelte:105 |
| D5 P1 | Fix date "Shift by" = `earlier` select + three spinners on two lines | FixDateDialog.svelte:86-96 |
| D6 P2 | Device sheet (desk-sheet): "Revoke" in red text inside a grey tile; Close bottom-right | admin/DeviceKeeps etc. |

**Flight — one `Sheet` primitive for every dialog:**
- **Phone:** bottom sheet, grab handle, 28 px top radius, glass header (title 17/650 centred,
  `Cancel` left text, primary action right as bold text — iOS nav-bar sheet), content in grouped
  inset cards (`--fill`, 14 px radius, 44–52 px rows, no lines, 8 px gaps). Detents: medium/large.
  Rises 380 ms `--ease-sheet`; drag-to-dismiss with velocity (> 0.8 px/ms closes), scrim follows.
- **Laptop:** centred sheet 480 px (wide 640), 28 px radius, `--raised`, scale 0.96→1 + fade 220 ms;
  same header layout; primary bottom-right as a full-height 44 px ink pill.
- **Controls:** replace native radios with **choice cards** (selected = ink ring 2 px + check,
  not accent), checkboxes with **iOS switches**, selects with **segmented** (≤4 options) or a
  menu row with value + chevron (`ActionMenu`), number spinners with **stepper** pills.
- **Download:** two big choice cards (Full size / Smaller with size estimate on each), a
  "Remove location" switch row, `Options ›` row that pushes a second page inside the sheet
  (slide left 280 ms): Format segmented, Quality slider, Size segmented, Metadata switch,
  ZIP names/folders as menu rows. Choice state never clears (fix D2).
- **Fix date:** segmented `Shift | Set`. Shift = a single "−1 h" style stepper row for days,
  hours, minutes with an Earlier/Later segmented; Set = date + time wheels (native
  `datetime-local` styled, or DateField). Live preview card: "7 Sep 2026, 09:01 → 7 Sep 2026,
  08:01" with the new value in 17/600. Fix the month-first note (D4).
- **Destructive:** confirmation = action sheet (phone) / small sheet (laptop), red text primary.

---

## 9. Toasts

| # | Issue | file:line |
|---|---|---|
| T1 P1 | Solid `--raised` slip, 20 px radius, shown/hidden by `display: none` (no motion) | +layout.svelte:227-256 |
| T2 P2 | Repositioning rules per context (selection pill, viewer) are ad hoc | +layout.svelte:257-266 |

**Flight:** glass capsule, 44 px, 15/500, optional leading icon (✓, ↓ progress ring for
downloads, ⚠), action as bold text ("Undo"). Phone: top, under the Dynamic Island, slides down
24 px + fade, 380 ms sheet curve; swipe up to dismiss. Laptop: bottom-centre above the
pill/bar. Auto-dismiss 4 s (8 s with an action). Keep the popover/inert logic.

---

## 10. Page transitions & motion spec

| Moment | Spec |
|---|---|
| Place switch (Home ↔ Library ↔ Collections) | cross-fade 200 ms `--ease` (exists: `switch`); dock lens slides with spring 340/30 |
| Push / pop (Collection → Album) | slide 30% + fade, 380 ms `--ease-sheet` (exists); add large-title → back-button label morph (P2) |
| Photo open/close | shared-element zoom tile ↔ photo (exists); radius 0 → 0; scrim black 0 → 1 |
| Sheets | 380 ms `cubic-bezier(.32,.72,0,1)` in; drag follows 1:1; release spring with velocity |
| Menus/popovers | scale .9 → 1 + fade, origin = anchor corner, spring 400/32 (~220 ms) |
| Press | `scale(.96)` controls, `.97` tiles/cards, 100 ms in, spring out |
| Chrome fade | opacity 200 ms `--ease` |
| Grid zoom | FLIP transforms, spring 300/30 (~320 ms) |
| Scrubber show/hide | opacity 160 ms / 300 ms |
| Reduced motion | all of the above → 120 ms opacity only; no scale, no slide |

Rule: only `transform`/`opacity`; no Svelte `$state` per frame for gestures (rAF + style).

---

## 11. Shared components to build

| Component | Replaces / used by | Notes |
|---|---|---|
| `Surface` (CSS: `.glass`, `.raised`, `.fill` + edge) | every bar, pill, menu, toast | G2/G5 tokens |
| `LargeTitle` (large → compact glass capsule on scroll) | PageHead, Library, Search, Album | scroll-driven animation + IO fallback |
| `ChipRow` + `Chip` (slim) | FilterChips, Search suggestions, Editor aspects | edge mask, snap |
| `ActionMenu` (glass, icons, groups, anchored) | Menu, SelectionBar More, viewer ⋯, long-press | one menu everywhere |
| `Sheet` (detents, header slots, push pages) | Dialog, FacetSheet, PhotoInfo phone, Download, FixDate | wraps `<dialog>` + `modal` + `sheetDrag` |
| `ChoiceCard`, `Switch`, `Stepper`, `Segmented` (restyle), `MenuRow` | Download, FixDate, Settings | no native radios/checkbox visuals |
| `Scrubber` | TimeRuler | vertical, hidden at rest, both devices |
| `GridZoom` (pinch/⌘± controller + FLIP) | Timeline, JustifiedGrid | 5 levels per device |
| `Tile` states (load fade, hover, press, select circle) | PhotoGrid | shared by every grid |
| `Skeleton` (justified blocks, single shimmer) | Library first load, Search, Albums | ≥150 ms delay |
| `GlassBar` (top / bottom capsule with fade) | Viewer, Editor | chrome idle handling stays in Loupe |
| `InfoCard` + `SpecRow` + `MiniMap` (offline world path) | PhotoInfo | no network tiles |
| `CoverCard` (photo, scrim, eyebrow, title) | Calendar Years/Months, Search Places, Home | shared with Home hero work |
| `Dial` | Editor straighten | |
| `Toast` (glass, icon, action, swipe) | +layout notice | |
| `spring.ts` | all gestural motion | stiffness/damping/velocity |

---

## 12. Needs backend / API change (ask before doing — AGENTS.md hard stops on schema)

| ID | What | Why | Fallback without it |
|---|---|---|---|
| A1 | `thumbhash` (or dominant colour) on `AssetOut` | blur-up placeholders in every grid | flat `--fill` + 180 ms fade |
| A2 | Bulk actions by filter scope (favourite/hide/delete/album on `{filters}`) | "Select all" beyond loaded pages | keep "Select loaded" semantics, label "Select all" only when `loader.done` |
| A3 | Facet count for a pending filter (if `/api/facets` doesn't give a total) | "Show 28 photos" button in filter sheets | apply live, count in chip |
| A4 | `/api/calendar?by=month` with a cover per month | Months mosaic | per-month `/api/assets?limit=1` calls (N requests) |
| A5 | Cover photo per place (facets) | Search Places cards | text chips (now) |
| A6 | Real count / paging for semantic + text search | honest "N results"; past 200 | "Top 200" label |
| A7 | Caption field on assets | Details title card | omit |
| A8 | Offline map tiles served by the home server | street-level mini map | world-outline dot map (`world.ts`) |
| A9 | Light/colour adjustments in the edit recipe + renderer | Editor Adjust tab | Crop-only editor |

Nothing above sends photo data or metadata off the machine; the mini map must stay offline.
