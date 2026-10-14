# UI redesign 2: calm, iconic, a story on Home

Date: 2026-10-14 · Status: approved by C (direction, chips, utilities, backup dot, Who chip,
Home built here, larger text prepared only)
Prototype: https://claude.ai/artifact/DNT6Q7q7JZSpdUWWqnrLVD (private to C; synthetic scenes)
Builds on: `2026-10-08-ui-redesign-design.md`, PR #64 (16 px root), issue #54 (Home), issue #10.

## 1. Goal

Every screen, phone first and laptop too, gets quieter and easier to move through: fewer
words where an icon is universally understood, no decoration without a job, one way to filter,
and a first page (Home) that tells the family's story. Motion is fluid and never stutters.
The design leaves room for a later "Larger text" mode for C's parents.

C's standing rules for this pass (2026-10-14): Tufte; no letter-spacing; no all-capitals; no
gradients; no 1 px strokes; remove dots, labels and texts that are there without a purpose.

## 2. Visual system

**Type.** Atkinson Hyperlegible Next (variable, 200–800, SIL OFL, self-hosted in
`web/static/fonts`, latin + latin-ext like today) replaces Hanken Grotesk _and_ Martian Mono.
It was drawn for readers with low vision, which is the Larger text mode's head start.
`--font-ui`, `--font-title` and `--font-data` all point to it (`--font-data` stays as a name so
nothing breaks; it means "tabular figures" now). Newsreader stays for the Album theme only.
Hierarchy comes from size and weight: titles 750, section heads 700, body 400, controls 600.
`letter-spacing` is 0 everywhere; `text-transform: uppercase` is not used anywhere; tabular
numerals stay on globally. Sizes keep PR #64's scale (12 · 14 · 16 · 20 · 28 · 40 at a 16 px
root). Display (`--fs-40`) is used on Home, a person and an album only.

**Colour.** Safelight values stay (darkroom page, amber accent for selection and focus only).
`--hairline` stops being a line colour: it remains only as a tile placeholder. A new
`--fill` (dark #23272D, light #E4E6EA, Album equivalents derived the same way) is the surface of
chips, fields, segmented controls and tiles on a raised sheet. `--lens` (ink at 14 %) marks the
chosen tab or segment. No gradients anywhere, including glass.

**Lines.** No borders or 1 px dividers. Groups separate by space; rows inside a group are tiles
separated by a 2 px seam (`--fine`; not `--gutter`, which the look's photo-gap dial moves and
may set to 0). Selection keeps its 3 px inset accent frame; focus keeps its 2 px accent outline.

**Icons.** Stroke 2 px (was 1.6), round caps and joins, 24 grid. New icons: home, select,
upload, plus, calendar, grid, pin (place), camera, person, sliders, play, inbox, hidden, moon,
sun, text-size, phone, lock, shield, signout, folder, cloud, disk, check, refresh, report,
power, sparkle, alert, pinned, chevrons (left, right, down), x. The prototype's paths are the
starting drawings.

**Icons over words.** Page and photo actions everyone knows are icons alone, each with its
accessible name and, on a laptop, a tooltip: select, upload, view switch, share, favourite,
add to album, edit, more, close, details, back. Words stay in the main navigation, in
sheet titles and in menus. The look's existing "words under icons" switch (today: dock only)
extends to every icon button; Larger text will turn it on.

**Glass.** Only on bars that float: dock, laptop top bar, compact page title, selection pill,
photo-view chrome, time ruler. Never on tiles or lists (cost and calm). Solid fallback rules
stay as in `utilities.css`.

**Motion** (only `transform` and `opacity`; nothing animates layout, size or blur):

| What        | How                                                                                                                                                           |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Press       | scale 0.95, 120 ms                                                                                                                                            |
| Sheets      | slide up with `cubic-bezier(.32,.72,0,1)`, 380 ms; drag down to close                                                                                         |
| Pages       | browser view transitions on the page area: drill-in slides from the right, Back slides from the left, tabs cross-fade (Safari 18+, Chrome; elsewhere instant) |
| Dock        | the chosen-tab lens slides to the new tab                                                                                                                     |
| Large title | scrolls away; a compact glass title fades in                                                                                                                  |
| Photo view  | opens from its tile and returns to it (exists); pull down to close follows the finger                                                                         |
| Favourite   | a short pop on the heart                                                                                                                                      |

`--motion-sheet` becomes 380 ms; DESIGN_PRINCIPLES rule 9's "≤ 240 ms" is rewritten to "presses
and fades ≤ 240 ms; sheets and pages up to 380 ms, on the sheet curve". Reduced motion keeps
everything instant. Long grids keep their windowing; nothing new runs on scroll except the
compact title class toggle and the ruler, both inside one `requestAnimationFrame`.

**Larger text, prepared.** Sizes and spaces are rem and follow the look's text dial; icon
buttons show their words when the root carries `data-words="all"`. A later mode sets that,
the text dial, a 56 px `--target` and a stronger `--ink-2`. No switch is built in this pass.

## 3. Shared pieces (new or reworked, in `web/src/lib/components/ui/`)

- `IconButton`: icon, accessible name, optional word (shown when the look asks), round 44 px.
- `Chip`: icon + label; pressed = ink fill; an × inside clears it.
- `Segmented`: icon or word segments with the lens.
- `TileGroup` / `TileRow`: the grouped list (icon, title, one quiet line, value, chevron or
  switch); a group label above with an optional icon action on the same line.
- `Switch`: the drawn toggle (ink when on; the accent is not used).
- `Sheet`: `Dialog` as a bottom sheet on a phone with a grab handle and drag-to-close; on a
  laptop an anchored popover (filters, menus) or a side panel (details). Back closes it (kept).
- `PageHead`: large title, a quiet line under it, actions on the right, the avatar; publishes
  the compact title on scroll.
- `Avatar`: the initial; a red dot for an admin when something needs them.

## 4. Navigation

Phone: floating glass dock with **Home · Library · Collections** (icon over word) and a round
**Search** button. The avatar sits at the right of each page's title row. Laptop: glass top bar
with the same three as icon + word, a search field in the middle, the avatar at the right.
The account menu goes; the avatar opens **You** (section 8). Trash and To review leave the
account menu for Collections → Utilities. The backup banner goes: members never see backup
state; an admin sees the red dot on the avatar and one plain sentence on You and on Admin.
The look's `showToday` / `startPage` switches start working: Home is the start page unless the
look says Library.

## 5. Library and filters

Title row: "Library", the count under it ("2,431 photos"), then grid/calendar (segmented
icons), Select, Upload, avatar. "Select loaded (200)", "Download all" and "Select all" leave the
header (select all lives in the selection pill's More). Month headings lose their counts.

Filters are a chip row under the title, the same on phone and laptop; the laptop's right
column is removed and the photos take its width. Chips: **Who · When · Where · Favourites ·
Camera · More**, then "Clear all" when two or more are set. A set chip shows its value ("Sam",
"July 2019", "Lisbon") with an ×. Favourites toggles in place; the others open a sheet asking
one question:

- Who: faces with names (needs the server's person filter, section 10).
- When: one bar per year with its count (zero-based, ink only, the chosen year in full ink);
  after a year, its twelve months as a 4 × 3 grid with counts; "Between two dates" with the
  existing day-first `DateField`s.
- Where: a find field over the places list (country under the name, count at the right), and
  "No place recorded".
- Camera: "Taken with" (cameras) and "Came from" (sources, several allowed).
- More: Show hidden photos; Only guessed dates.

Counts in a sheet are those of the other filters (as the facet merge does today). The URL keeps
every filter (unchanged contract). The time ruler stays as the signature, restyled: years in
the UI face, no capitals, the needle a filled accent pill with the month in view.

The selection pill: × (stop), "3 selected" with the number in accent, then icons Add to album,
Share or Download, Move to trash, More. Overflow rules stay.

## 6. Photo view

Round glass Close (chevron down) and Details (i). The bar: line one date, time, place; line two
camera, aperture, shutter, ISO, spaced by gaps instead of dots, in the UI face. The file name
moves to Details. Actions are icons: Favourite, Share (or Download), Add to album, Edit, More.
Details is a sheet on a phone and the side panel on a laptop, laid out as label/value tiles.
Pull down to close, swipe sideways, double-tap zoom: unchanged.

## 7. Collections, a person, an album, Trash, To review, Search

Collections: People (faces and names, no counts), Places (4:3 covers, a plain number), Albums
(a grid of covers with a plain number, + for a new album), then **Utilities**: To review, Hidden,
Trash, each a tile with its count.

A person: centred portrait, the name in display size, "27 photos, 2012 to 2026", then Play
(primary) and In Library; Rename, Change portrait, Merge with…, Hide behind a round ⋯. Photos
grouped by year.

An album: the cover leads (full width on a phone, beside the title on a laptop), title in
display size, "12 photos, July 2024", then Play, Add photos, Share, ⋯.

Trash: one sentence ("Photos are deleted for good 30 days after they arrive here. Your
original files are never touched."), Select and ⋯ (Restore all, Empty trash) in the header,
each tile shows its days left. To review: grouped by reason, one decision per group.

Search: field first, then suggestions before typing: faces, places as chips, things as chips.

Play opens the story player (section 9) for that person, album or memory.

## 8. You and Admin

**You** (from the avatar): initial, name, role; Look (mode as a segmented Dark/Light/Device);
for an admin, a "Needs you" tile when something does (the dot's sentence); Phones that send
photos here (the device list, + to add); Account (Change PIN opens the PIN pad in a sheet, Sign
out). Admin is a tile here for admins.

**Admin**: status first, three tiles: Backups (dot and one sentence), Library (photos and free
space), Problems (count). Then Folders, Search and faces, People, each a tile group with its +
action on the label line. A tile opens a sheet with its actions as icon cards (Check now, Who
sees it, Report, Turn off…) and its details (paths and commands live here, admin only).
Backups, Recent runs, Recovery key and the look form open from their tiles.

## 9. Home (issue #54, first version)

Read top to bottom like a story, each block shown only when it has photos:

1. Date line ("Wednesday 14 October") and the avatar.
2. **On this day**: the best photo from this date in earlier years, full width, a display title
   ("Three years ago today") and one line (place, people). Play.
3. **Memories**: a sideways row of 3:4 covers, each a period put together automatically (a trip:
   photos close in time and place), title and dates. Play.
4. **Pinned**: the account's chosen photos as a justified block; "Choose" edits them.
5. **People**: faces.
6. **New this week**: one sentence ("42 photos arrived from Léa's iPhone") and the newest photos.

The story player: full screen, one photo after another with a slow push-in (transform only),
progress segments at the top, title in a glass caption, tap right/left for next/previous,
Escape/× or pull down to close. Music is the next step (issue #54 decisions) and not built here.

## 10. Server changes

- **Person filter**: `person_id` (repeatable) on the asset list and facets, as a URL filter like
  the others; mock API mirrors it. Contract version bump in `docs/contracts/api-v1.md`.
- **Home**: what the first version needs and what already exists is listed in the plan after
  the code survey; any new table (pinned photos per account) follows issue #54 and the
  migration-number rule (check `origin/main` before numbering).

## 11. Order of work and ownership

1. Foundation (one branch, merged first): fonts, tokens, icons, shared pieces, docs. Starts when
   PR #64 is on main. Server person filter and Home data in parallel (backend only).
2. Areas in parallel, one branch and owner each: (a) navigation, You, backup dot; (b) Library,
   filters, ruler, selection; (c) photo view; (d) Collections, person, album, Trash, To review,
   Search, Admin; (e) Home and the story player.
3. Files another session has in flight are restyled after those PRs merge: `Sources.svelte`,
   `Devices.svelte`, `PhotoInfo.svelte`, `DownloadDialog.svelte`, `readout.ts`, and the
   album/person/search/library pages (the "Keep on my phone" switch).

## 12. Testing

Each branch: unit tests for new logic (chip labels from filters, facet counts, Home blocks,
story player steps) written first; the e2e specs of the screens it touches. Once, at the end:
`just check`, `just e2e`, `just e2e-mock`, and the screenshot set re-rendered (dark and light).
`fit.spec.ts` and `type.spec.ts` (from #64) are re-run after the font change; any changed
assertion says why in its PR.
