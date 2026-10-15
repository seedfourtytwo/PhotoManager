# Collections, Albums, People, Places: review + Flight spec

Scope: `/collections`, `/albums`, `/albums/[id]` (+ share, add-to-album, new album, rename/delete),
`/albums/[id]/print`, `/people`, `/people/[id]` (+ portrait picker, merge), `/map`.
Sources: every screenshot listed in the brief (desktop 1440x900, phone 390x844), plus the code.
Target: `../design-system.md` ("Flight"). Paths are relative to `web/src/` unless they start with `backend/`.

Math used below. Laptop content width at 1440 = 1440 − 2×32 = **1376 px**. Phone = 390 − 2×16 = **358 px**.
Grid gap = 16 px for cards and 2 px for photos. "No ragged ends" means a strip shows exactly
`cols × rows` items (the "See all" page holds the rest), or it is a rail that bleeds off the right edge.

---

## 0. Problems on every screen in this area

| # | Problem | Where |
|---|---|---|
| 1 | Page background is `#0d0f12`, not true black. Photos sit on a grey-blue tone. | `lib/themes.css:13` |
| 2 | Opaque header strip; on phone the album and person pages lose the top 144 px to a solid bar. | `PageHead.svelte` (used by all routes here) |
| 3 | Hover is a text underline (`text-decoration: underline`), which reads like a web document rather than an app. No press scale and no lift. | `CollectionRows.svelte:430-436`, `albums/+page.svelte:129-134`, `people/+page.svelte:174-179` |
| 4 | Captions sit under the photos (name, then count) instead of on them, so each card takes about 40% more height. | `CollectionRows.svelte:281-285`, `albums/+page.svelte:69-77` |
| 5 | Counts use the `.data` tabular face, so "107" looks like code. | `CollectionRows.svelte:222-225` |
| 6 | Loading shows empty `min-height` boxes (no shimmer), or the word "Loading…". | `CollectionRows.svelte:359-364`, `albums/[id]/+page.svelte:168` |
| 7 | Dialogs are centred cards on laptop and plain sheets on phone, with native `<select>` and radio controls inside. | `Dialog.svelte`, `PeopleEditor.svelte:37,46` |
| 8 | Photo gutters in grids look like 4 px on laptop and about 8 device px on phone, against a spec of 2 px. This comes from `settings.gap`. | `albums/[id]/+page.svelte:44`, `map/+page.svelte:141` |

---

## 1. Collections (`/collections`)

### What is wrong, ranked
1. **Ragged rows on laptop.** Places wrap at a fixed `12rem` with `flex-wrap`, so 7 places show as 6 plus an orphan (Chamonix), with 180 px of dead space on the right of row 1. The Albums row starts at y=838 and is cut off by the fold. `CollectionRows.svelte:437-445`
2. **People are small and packed to the left.** Six 76 px faces take up 580 of 1376 px. `CollectionRows.svelte:248,379-383`
3. **Phone people rail has no visible "more".** Four faces fill exactly 390 px, so the two unnamed people are off-screen with no peek. `CollectionRows.svelte:382`
4. **Utilities ("To review", Hidden, Trash) sit under the dock on phone.** The bottom padding is `--s-7`, which is smaller than the dock. `collections/+page.svelte:18`
5. **Places is 1 + up to 16 requests.** The page calls `facets`, then `assets(place, 1)` for each of `STRIP_LIMIT*2` places. `CollectionRows.svelte:207-219` (backend flag B2)
6. Every card is the same 4:3 frame with a caption below, so the three rows have no distinct identity. `CollectionRows.svelte:389-395`
7. On laptop the album "+" floats beside the heading. `CollectionRows.svelte:453-455`

### Flight spec
| | Laptop (1376 content) | Phone (358 content) |
|---|---|---|
| Page title | iOS large title "Collections" 34/700. It collapses into the glass bar on scroll. | Same, 34 px. |
| Order | People, Albums, Places, Utilities. Albums move above Places because they are curated, so they rank higher. | Same |
| **People row** | 8-col grid, gap 24. Each FaceBubble = (1376−7×24)/8 = **151 px** circle. Name 15/600 under the circle, count 13 `--ink-2`. Exactly 8 (already `STRIP_LIMIT`). | Rail of 76 px bubbles, gap 16, which shows **4.4** and peeks the 5th. Bleeds to the screen edges. |
| **Albums row** | One row of 4 **square** CoverCards: (1376−3×16)/4 = **332×332**, title on photo. If there are fewer than 4, the last slot is a "New album" tile. | Rail of square cards at **2.3 visible**: 148×148, gap 12. |
| **Places row** | Rail of **3:2** CoverCards at 4.3 visible: ≈ 306×204. Bleeds right; glass ‹ › arrows show on hover. Place name on photo, count as a caps eyebrow. | Rail of **4:5** cards at 2.3 visible: 148×185. |
| Section header | `SectionHeader`: 22/650 title plus chevron (the whole thing is a link), trailing "See all" in 15 `--ink-2`, and the "+" as a glass round button at the far right. | Same |
| Utilities | One glass group of 3 rows (icon, title, count, chevron), max width 560 px, left-aligned. | Full width. Bottom padding = dock height + 32 + safe area. |
| Empty row | People: the row is hidden until faces exist, and the admin sees one quiet line. Albums: a single "New album" tile. Places: the row is hidden. | Same |

Motion: cards enter staggered (30 ms each, opacity plus 8 px rise, once per visit). Press scale 0.96 for 100 ms. On hover (laptop) the image scales to 1.03 inside its clip and the scrim deepens. A card tap starts a **shared-element** transition into the album, person or place hero (see §8).

---

## 2. Albums list (`/albums`)

### What is wrong, ranked
1. `auto-fill minmax(14rem)` puts 2 albums in 571 of 1392 px and leaves the rest of the screen empty. `albums/+page.svelte:96-98`
2. The 4:3 cover has its caption below, and "12, shared with you" reads as a broken sentence. `albums/+page.svelte:73-77,108-113`
3. My albums and shared albums are not separated. Apple Photos separates them, and the partner will expect that.
4. The empty state is two paragraphs of text with nothing to tap except a "+" in the corner. `albums/+page.svelte:55-63`

### Flight spec
- Grid: `repeat(auto-fill, minmax(300px, 1fr))` using container width, gap 16. That gives **4 cols × 332 px squares** at 1440, 5 cols at 1680+, and **2 cols × 171 px** on phone. Squares fill the width exactly; only the last row can be partial, and it stays grid-aligned.
- Card = `CoverCard variant="album"`: square photo, 28 px radius (a card, not a grid photo), `--scrim-photo`, title 17/650 bottom-left on the photo, count 13 tabular. A shared album gets a small glass "people" badge top-right.
- Sections: "My albums" and "Shared with me" (22/650 headers), only when both exist. Optional sort as a glass segmented control: Recent / A–Z (client-side, using `updated_at`).
- "+" is a glass round button in the top bar and opens the New-album **sheet**.
- Empty: one `CoverCard variant="new"` (a `--fill` square with a 44 px "+" glyph and "New album"), plus one line: "Or select photos in Library and choose Add to album."

---

## 3. One album (`/albums/[id]`)

### What is wrong, ranked
1. **The hero is half empty on laptop.** It is a 28rem cover on the left with the title floating in a void on the right (about 900×336 of nothing). `AlbumHero.svelte:390-399`
2. **On phone the title sits under the photo, not on it.** A 4:3 cover below a solid 144 px header pushes the photos below the fold (the first photo starts at y≈1350 of 1688). `AlbumHero.svelte:324-348`
3. The **cover is the 640 px thumbnail**, which goes soft at hero size. `backend/.../api/schemas.py:405` (backend flag B1)
4. On phone the Keep-on-phone icon wraps alone onto a second line. `AlbumHero.svelte:368-374` together with the `KeepOnPhone` in `albums/[id]/+page.svelte:113-115`
5. The description uses the serif/italic "voice" font, against the spec's "no serif in default look". `AlbumHero.svelte:355-362`
6. The grid is inset by `--page-x` on laptop, so it is not edge to edge. `albums/[id]/+page.svelte:248-250`
7. Arrange mode is a sentence with a text button. `albums/[id]/+page.svelte:124-128`

### Flight spec: `CollectionHero` (shared with Person and Place)
| | Laptop | Phone |
|---|---|---|
| Frame | Full-bleed 1440 wide, height `min(64vh, 600px)`, under the floating glass top bar. | Edge to edge, **4:5** (390×488), under the status bar. Back and ⋯ are glass circles on the photo. |
| Image | Cover at preview resolution, `object-fit: cover`, slow Ken Burns drift (scale 1.0→1.06 over 20 s, transform only). | Same, no drift under reduced motion. |
| Type on photo (bottom-left, 32 px inset) | Eyebrow 11-caps "ALBUM · 2017–2024" (or "SHARED BY LÉA"), title `--fs-display` 56/700, description 17/500 `--ink-2`, line "24 photos" 13 tabular. | Title 40/700 (wraps at 2 lines, then ellipsis), the rest the same. |
| Actions | A glass capsule bottom-right on the photo: **Play** (ink pill), Add, Share, Keep on phone, ⋯. Icon buttons are 44 px with labels in tooltips. | One row under the title, still on the photo: Play pill, then round glass Add, Share, Keep, ⋯. Never wraps; ⋯ absorbs overflow. |
| Scroll | Scroll-driven (`animation-timeline: scroll()`): the photo moves at 0.5× (parallax) and dims to 40%. The title cross-fades into the top bar as a 17/600 inline title (iOS large-title collapse). | Same. |
| Grid | Justified photos, **2 px gutters, edge to edge**, starting right under the hero. | Same. |
| No cover / empty album | Hero becomes a `--raised` panel 40vh tall: title, then "Add photos" as the primary pill. | Same. |

Arrange mode: the top bar becomes "Arrange · Done" (glass). Tiles jiggle-free; the dragged tile lifts (scale 1.04 + `--lift`) and the others spring aside (FLIP).

### Share dialog (`ShareDialog.svelte`, `PeopleEditor.svelte`)
Problems:
1. A native `<select>` plus a separate "Add" button means two steps to add one person (`PeopleEditor.svelte:46-50`).
2. Role is a native select and Remove is a text link (`:37-40`).
3. There are no faces or avatars.
4. Changes are not live; Cancel/Save are explicit.

Spec: a **Sheet** (spring rise, 28 px top radius, glass over scrim; on laptop it is a 440 px popover anchored to the Share button).
- Members are listed as rows: Avatar initial, name, then a role segmented control "Viewer | Editor", with swipe-left (phone) or hover ✕ (laptop) to remove.
- "Add people" is a tappable list of directory entries not yet added (Avatar plus name, one tap adds them as Viewer).
- It saves on close, and an Undo toast covers mistakes.
- **Contract caveat:** Save replaces the whole member list (`ShareDialog.svelte:410-412`). Auto-save must keep the "only after the list loaded" guard.

### Add to album (`AddToAlbumDialog.svelte:52-77`)
Problems: it is a text-only radio list, has no covers, and needs a "New album" radio before the title field appears.

Spec: a Sheet with a **grid of square covers** (3 cols on phone at 108 px, 5 cols on laptop popover). Tile 1 is "New album…", which turns into an inline title field. One tap on a cover adds the photos and closes the sheet, with a toast "Added 3 to Brittany" and an Open action. Editable albums only (as now).

### New album (`NewAlbumDialog.svelte`)
Spec: a Sheet with a big 28/650 title field (autofocus, placeholder "Album name") and the description as a second, quiet field. "Create" is the primary pill and opens the album with the shared-element hero (empty-album state).

### Rename / Delete
Spec: Rename is inline-editable on the hero title, using the same ⋯ entry. Delete is an action sheet with a red destructive row. The copy stays the same.

---

## 4. Album print layout (`/albums/[id]/print`)

### What is wrong, ranked
1. **On phone the previews sit below the form** and behind the dock. "Download PDF" scrolls away. `print/+page.svelte:282-292`
2. It uses a crumb link (an underlined album title) instead of the back pattern. `print/+page.svelte:193-198`
3. The controls are native: a size `<select>`, radios, checkboxes, and serif "Aa" swatches. `print/+page.svelte:105-131,221-230`
4. The resolution issue is a dense sentence with a 40 px thumbnail. `print/+page.svelte:144-155`
5. The page grid's last row is ragged (12 pages: 5+5+2). This is acceptable for a page list.

### Flight spec
| | Laptop | Phone |
|---|---|---|
| Layout | Two panes. Left: a **page viewer** that takes the remaining width (pages at true trim aspect on `--bg`, 2-up spread, ‹ › and thumbnails strip below). Right: a 360 px glass inspector. | Full-bleed page carousel at the top (swipe pages, 1 at a time, dots). Inspector as a **bottom sheet** with 3 detents (peek: size + Download; half; full). |
| Inspector | Size as a menu-button chip; Theme as 3 swatch cards (paper colour, "Aa" in the theme's real face, as now); Cover / Crop marks as toggles (switches, not checkboxes); summary "12 pages · A4 landscape · 24 photos" 13 tabular. | Same, inside the sheet. |
| Resolution | A warning row with an amber dot: "1 photo may print soft". It expands to a row of thumbnails (64 px) with ppi; tapping one jumps the viewer to its page. "Print anyway" is a toggle. | Same. |
| Primary | "Download PDF" is an ink pill pinned at the bottom of the inspector (always visible) and shows progress while building. | Pinned in the sheet's peek. |

Motion: a page change slides with a spring. A theme change cross-fades previews (keep the old image until the new one decodes, so it never flashes white).

---

## 5. People (`/people`)

### What is wrong, ranked
1. **Four 84 px circles are packed to the left of a 1376 px canvas**, with ~70% of the screen empty. `people/+page.svelte:9,129`
2. The "Named / Not named yet" headings split a list of 6 into two sparse sections. `people/+page.svelte:71-85`
3. The ML status note is grey admin text at the top of the page, so the partner sees "Set it up in Admin". It is admin-gated only for the link. `people/+page.svelte:53-58`
4. No photo counts and no hierarchy: everyone is the same size, so family looks no different from a stranger.
5. Hidden people sit in a `<details>` disclosure with tile rows. `people/+page.svelte:87-106`

### Flight spec
| | Laptop (1376) | Phone (358) |
|---|---|---|
| Top band "Most seen" | The top 4 named people by `asset_count`, as **4:5 photo cards** (4 × 332 → **332×415**, gap 16). Each uses the portrait's **source photo** (`portrait.asset_id` → `api.previewUrl`) with `object-position: cx% cy%` so the face is centred. The name is 28/700 on the photo and the count is an eyebrow. | 2 × **171×214** cards. |
| Everyone else | FaceBubble grid `repeat(auto-fill, minmax(136px,1fr))`, gap 24, giving **8 cols × 151 px** circles at 1440. Name 15/600, count 13 `--ink-2`. | **3 cols × 108 px** circles, gap 16. |
| Unnamed | Same grid after the named people, with a dimmed name "Add name" in `--ink-2` (no italic). Tapping the name opens the name sheet directly. | Same. |
| Hidden | A trailing glass row "Hidden people · 3 ›" opens a sheet with the list and "Show again" buttons. | Same. |
| ML not ready | Admin: one glass banner card with "Faces are paused · Set up ›". Member: nothing, or a neutral "New faces are found overnight." | Same. |
| Empty | 64 px face glyph, "No people yet", one line explaining. No admin jargon for members. | Same. |

Note: the portrait is cut at **320 px max** (`backend/.../app/portraits.py:21`), which is fine for circles ≤160 px. Anything larger (the cards and the hero) must use the source photo, as specified.

Motion: a bubble press scales to 0.96. Tapping a person does a shared-element zoom from the bubble or card to the person hero (§8). Merge (from the person ⋯) animates the merged bubbles flying into the target.

---

## 6. One person (`/people/[id]`) and portrait picker

### What is wrong, ranked
1. **About 470 px (laptop) and 840 px (phone, half the screen) of chrome before the first photo.** The layout is a centred column: 148 px grey circle, name, line, actions. `PersonHero.svelte:557-563,526`
2. **Year groups leave ragged short rows.** The 2026 row ends at x=873 of 1416, and on phone 2025 ends in a single orphan tile. `people/[id]/+page.svelte:372-386` (`grouping={groupByYear}`)
3. "In Library" is a plain text link and Keep on phone is a bare unlabeled icon, sitting next to a filled Play pill, so the actions are three different styles. `people/[id]/+page.svelte:357-365`
4. Unnamed shows as "Someone" in italic (`PersonHero.svelte:582-586`), with renaming hidden in ⋯.
5. Merge is a checkbox list in a dialog. `people/[id]/+page.svelte:426-448`

### Flight spec
- Use the same **`CollectionHero`** as the album. The image is the portrait's source photo (preview size, `object-position` from `cx/cy`). Laptop is `min(64vh,600px)` full-bleed; phone is 4:5.
- On the photo, bottom-left: a **72 px FaceBubble** (tap opens the portrait editor, for editors), then the name `--fs-display`, then "27 photos · 2012–2026".
- Unnamed: a glass pill "Add name" replaces the title.
- Actions capsule, the same as the album: Play, Show in Library (round glass button with the grid icon), Keep on phone, ⋯ (Rename, Change portrait, Merge…, Hide).
- Grid: **one continuous justified mosaic**, 2 px gutters, edge to edge. Years are not row breaks. Each year is a sticky glass eyebrow chip ("2025") floating top-left as you scroll, as on Library. This removes the ragged per-year rows. (`Timeline` belongs to the Library area, so flag the change to its owner; the alternative is a `fillLastRow` option on `justify()` that stretches the last row up to 1.6×.)
- Merge: a sheet showing a FaceBubble grid. Tapping a bubble selects it (amber ring = accent's selection job), and the primary pill reads "Merge 2 into Sam".

### Portrait picker (`PortraitDialog.svelte`)
Problems:
1. It is a 20rem grey square stage inside a dialog, with the circle window over a light-grey surround (`:236-247`).
2. The 56 px face strip is clipped at the edge with no peek padding (`:216-224`).
3. It uses a native range slider labelled "Zoom".
4. "Use automatic" looks disabled.

Spec: a **full-screen black editor**, like the iOS crop tool.
- Photo stage fills the viewport. The outside of the circle is dimmed to `rgb(0 0 0 / .6)`, with a 1 px white 30% circle edge (the one allowed edge: it is a tool).
- Drag and pinch as now. Add a double-tap to fit the face.
- Bottom glass tray: a rail of 64 px face candidates (selection = amber ring), then a row with "Automatic", Cancel and Done.
- Remove the slider (pinch and wheel already exist); keep the +/− keys for accessibility.
- Laptop: the same, as a centred 720×720 stage inside the full-screen black.

---

## 7. Places / Map (`/map`)

**Tile source:** there are no tiles. The map is our own SVG: one land path from **Natural Earth 1:110m** (`lib/world.ts`, generated by `web/scripts/make-world.ts`) in plate carrée. It works fully offline, needs no keys, and nothing leaves the machine. Dark styling is already possible and costs nothing. MapLibre GL with self-hosted PMTiles was the plan and was dropped (`docs/TECH_DECISIONS.md:123-125`).

### What is wrong, ranked
1. **There is no pinch-zoom on phone.** Only one-pointer pan is handled, so the phone has only the "Zoom in/out" text buttons. `map/+page.svelte:198-211`
2. **The map is a fixed 2:1 strip.** On phone it is a 195 px band; on laptop the world view is 720 px tall and runs under the fold. `map/+page.svelte:74,343-348`
3. **It does not fit to the photos on load.** It starts at the whole world (`:73`), so a family library (France plus California) occupies a few dots. In the screenshot only 39 of 219 photos are visible on screen.
4. **The zoom floor is about 6° wide (≈660 km)** (`:99`), and the 110m coastline is blocky near that. You cannot get to town level.
5. Naming mismatch: Collections calls it "Places" (`lib/nav.ts:45`) but the page says "Map". There is no back button to Collections.
6. Clusters are flat amber/ink dots with the count set beside them in 11 px text (`:216-248`), where Apple shows photo bubbles. The count text overlaps neighbours.
7. The chosen-cluster panel is below the map, with the sentence-button "Open all 39 from Montara in the library" and an explanatory paragraph. `map/+page.svelte:252-286`
8. Panning writes `$state view` on every pointermove, which re-rasterises the full land path each frame. Expect jank on phone. `map/+page.svelte:202-209`
9. Zoom in / Zoom out / World are text buttons in the title row. `map/+page.svelte:183-187`

### Flight spec
| | Laptop | Phone |
|---|---|---|
| Frame | **Full-bleed map that fills the viewport** under the floating top bar (no page title strip). | Full screen, with the dock floating over it. |
| Style | Sea `#000`, land `#1C1D20`, coast 0.5 px `rgb(255 255 255 / .08)` (non-scaling stroke). Optional faint graticule at 2% white. | Same. |
| Initial view | **Fit to the bounds of `points`** plus 10% padding, clamped (a new `fitView()` in `lib/geo.ts`, pure, unit-testable). A "World" glass button resets the view. | Same. |
| Clusters | **Photo bubbles**: a 44–64 px rounded-square (12 px radius) thumbnail of the newest photo in the cluster, a 2 px white ring, and a glass count badge top-right. Built from the `located` map that is already loaded (`:76-90`), so no API change is needed. Bubbles never overlap (the existing cluster radius uses the bubble size). | 44 px bubbles. |
| Controls | A glass vertical stack bottom-right: +, −, fit-all. Filter chips float as a glass row top-left under the bar. | Chips as a horizontal glass rail at the top; + and − are hidden (pinch). |
| Chosen cluster | A right **glass panel** 400 px wide: hero strip (place name 28/700 on the first photo), count, "Show in Library" pill, then a 3-col square grid. | A **bottom sheet** with detents: peek (place name + count + 4 thumbnails), half (grid), full. The map stays live above. |
| Empty | The dark map stays visible, with a centred glass pill "No photos with a location yet" and one line below. | Same. |

Motion and performance:
- Pan with inertia (velocity decay) and zoom with a spring.
- Pinch through 2-pointer tracking (the pattern already exists in `PortraitDialog.svelte:76-96`).
- Apply the view as a CSS `transform` on a `<g>` during the gesture, and commit `viewBox` and clusters on settle. Stop recomputing the land path per move.
- When clusters split on zoom, children animate out from the parent position (transform only).
- Choosing a cluster flies to it over 300 ms.

Getting closer than country level, with no new dependency: regenerate `world.ts` from Natural Earth **1:50m**, and swap in 1:10m above a zoom threshold, through the same script. Both are bigger static assets, so measure them against PERFORMANCE.md. Street-level dark tiles need MapLibre plus self-hosted PMTiles, which is a **new dependency** (hard stop: owner decision; it can be fully offline, but the file size grows steeply with max zoom).

A places grid page ("See all" from the Places row) is optional. It would use the same CoverCard 3:2 grid and needs B2.

---

## 8. Shared-element and page motion (one mechanism)

- The infrastructure already exists: `onNavigate`, then `motion.ts` (`withTransition`, push/pop), plus the loupe pattern that sets `view-transition-name` on the tapped tile (`lib/loupe.svelte.ts:127-133`).
- Card to hero: on tap, set `view-transition-name: cover` on the card's `<img>` and `cover-title` on its title. The hero's `<img>` and `h1` carry the same names. On Back, set the names on the matching card again (find it by id) so it zooms home.
- Bubble to person hero: View Transition snapshots are bitmaps, so a border-radius does not morph by itself. Animate `::view-transition-group(cover)` with a `clip-path: circle()` → `inset(0)` keyframe instead.
- Durations: 420 ms `cubic-bezier(.32,.72,0,1)` for the shared element, with surrounding content fading 200 ms. Reduced motion means a plain cross-fade.

---

## 9. Shared components to build once

| Component | Used by | Notes |
|---|---|---|
| **CoverCard** | Collections rows, Albums, Places, Add-to-album, New tile | Props: `src`, `aspect` (`1/1 \| 3/2 \| 4/5`), `title`, `eyebrow`, `count`, `badge`, `href`, `vtName`, `variant: photo \| new`. Title on `--scrim-photo`, 28 px radius, press 0.96, hover image 1.03. |
| **Rail** | Collections (People, Albums, Places on phone), portrait candidates, map peek | Snap-scroller that bleeds to the screen edges, with a `visible` prop (4.3 / 2.3) that sets the item width so a peek always shows. Glass ‹ › on hover (laptop); keyboard arrow support. |
| **FaceBubble** | Collections, People, Person hero, Merge, Share (member avatars fall back to Avatar) | Wraps `Portrait`, adds name and count, `size` from the grid (100% of the cell), selected ring (accent) and press. Replaces 4 ad-hoc uses of `Portrait`. |
| **FaceCard** | People "Most seen" | A 4:5 source-photo crop at the face (`cx/cy` to `object-position`), with the name on the photo. |
| **CollectionHero** | Album, Person, Place panel/hero | Replaces `AlbumHero` and `PersonHero`. Full-bleed, title on photo, eyebrow, line, `actions` capsule, scroll collapse into the top bar, empty state. |
| **ActionCapsule** | Heroes, print inspector | Glass capsule: one primary ink pill plus round glass icon buttons. It never wraps; overflow goes into ⋯. |
| **SectionHeader** | Collections, People, Albums sections | Title + chevron link, "See all", trailing glass action. |
| **Sheet** | Share, Add to album, New album, Merge, Hidden people, Map cluster, Print inspector (phone) | Detents, a grab handle, spring, glass. Becomes an anchored popover on laptop. A `Dialog.svelte` successor. |
| **Segmented** | Share roles, album sort | Glass pill with a sliding lens, the same as the nav. |
| **EmptyState** | All screens | Glyph (48–64 px), one 17/600 line, one 15 `--ink-2` line, optional primary pill. |
| **Skeleton** | Rows and grids while loading | Shape-matched `--fill` blocks with a 1.2 s shimmer (transform on a gradient). Replaces "Loading…" and blank min-heights. |
| **PhotoBubble** (map) | Map clusters | Thumbnail + count badge, sized from the cluster radius. |

---

## 10. Backend / API changes to flag (and the ones that are not needed)

| # | Need | Why | Change |
|---|---|---|---|
| B1 | **Album cover at preview size + its asset id and w/h** | The hero and shared element are full-bleed, but `cover` is the 640 px thumb (`backend/.../api/schemas.py:405`). | Add `cover.asset_id`, `width`, `height`, `preview_url` to `AlbumSummary` (contract change). Do not have the client rewrite `/thumb` to `/preview` in URLs. |
| B2 | **`GET /api/places`**: name, kind (country/city), count, cover `{asset_id,url,w,h}`, centroid lat/lon | Collections makes 1 + 16 requests for 8 cards (`CollectionRows.svelte:207-219`), and a Places grid page would multiply that. | New endpoint (or `facets.places` with covers). |
| B3 | Favourite / pinned people (optional) | "Most seen" uses `asset_count` for now. Apple-style favourites need a stored flag. | Schema change: owner decision. |
| B4 | Album sharer name for the "SHARED BY LÉA" eyebrow (optional) | `AlbumSummary` has `owner_id` and `role`, but no owner name for members. | Add `owner_name`, or have the client join with `userDirectory()` (no backend change). |
| no | Person hero photo | `portrait.asset_id` + `cx/cy` is already enough. | none |
| no | Map photo bubbles | `located` already holds an `AssetOut` with a thumb for each point. | none |
| no | Dark map | Our own SVG, offline. | none (more detail is a data regeneration; tiles are a new dep, hard stop) |

Cross-area touches to call out in PRs: `Timeline`/`justify` (Library area) for the continuous person mosaic; `Dialog` to `Sheet` and `PageHead` to the glass top bar (shell/UI area); `--bg` true black (`themes.css`).
