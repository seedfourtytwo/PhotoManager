# UI redesign: identity, flow and per-account look

Date: 2026-10-08 · Status: draft for C's review
Mockup: https://claude.ai/artifact/RdL2LJ3w5i5r5fyxAJPYj8 (private to C)
Terms: `CONTEXT.md` · Decision record: `docs/adr/0001-look-is-a-validated-sheet-not-css.md`

## 1. Goal

Make the app enjoyable to browse on a phone and a laptop with as few taps as possible, give it
an identity between modern Apple and geek/techno, and let each account carry its own look that
C sets (and later a local AI model changes from a sentence) without anyone touching CSS.

Audience: C, C's partner, C's mother and possibly her partner. Mixed technical level, so the
geek side is light on everyday pages and loud only on System.

"Mobile" means the same web app installed to the iPhone home screen. No native app.

## 2. What stays, what goes

Kept from `DESIGN_PRINCIPLES.md`: photos edge to edge at true aspect ratio, 2–4 px gutters, one
accent used for selection and focus, layering by value, tokens as the only source of colours
and sizes, same information architecture on laptop and phone, AA contrast, reduced motion.

Reversed:

| Today | New |
|---|---|
| Words, no icons | A small drawn icon set; nav and action bars show icon **and** label |
| Serif titles (Newsreader) | Sans titles; serif survives only in the Album theme |
| Flat page, hairlines only | Floating translucent bars ("glass") over the photos |
| Motion ≤ 150 ms, only to explain | Up to 240 ms; sheets and the photo view move with the finger |
| No status colours anywhere | Green/red dots allowed on the System page only |
| 8 nav items, fixed filter column, Search page | 3 places and one search |

`DESIGN_PRINCIPLES.md` is rewritten to match in part A.

## 3. Identity: the Safelight theme

A darkroom, with camera data on the readouts.

**Colour** (token names unchanged so components keep working; values change):

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | #0D0F12 | #F2F3F5 | page |
| `--raised` | #171A1F | #FFFFFF | sheets, bars, menus |
| `--ink` | #F1F2F4 | #14161A | text, primary fill |
| `--ink-2` | #A3A9B3 | #565D68 | secondary text |
| `--ink-3` | #6B717C | #8A909A | decoration, disabled |
| `--hairline` | #262A31 | #DCDFE4 | dividers, placeholders |
| `--accent` | oklch(0.82 0.14 H) | oklch(0.50 0.15 H) | selection, focus, "now" on the ruler; H = 72 (amber) |
| `--on-accent` | #17110A | #FFFFFF | text on accent |
| `--glass` (new) | `--raised` at 74 % + blur | same | floating bars |
| `--ok` / `--fail` (new) | #7BD3A0 / #FF7A6B | darker pair, AA on `--bg` | System page status only |

The accent's lightness and chroma are fixed per mode and only the hue is a dial, so any hue
stays readable without a contrast checker.

**Type** (self-hosted in `web/static/fonts`, SIL OFL, nothing fetched at runtime):

- **Hanken Grotesk** (variable) — `--font-ui` and titles. Titles 720 weight, tight tracking.
- **Martian Mono** (variable, set at 80 % width) — `--font-data` (new): dates, counts, camera
  settings, file names, system status. Never for anything you tap or read as a sentence.
- **Newsreader** — kept only as the title face of the Album theme.
- Instrument Sans is removed. Both new fonts are recorded in `TECH_DECISIONS.md`.

**Shape and motion:** `--r-1` 12 px (controls), `--r-2` 20 px (sheets, hero cards), `--r-pill`
(new) for the dock and chips. Photos in grids stay square-cornered. `--motion` 200 ms,
sheets 240 ms; off under `prefers-reduced-motion`.

**Glass rule:** smoothness wins. Blur only on the small floating bars; measured by the
existing perf test against the 60 fps budget. If it misses, the bars turn solid `--raised`.
Also solid under the device's "reduce transparency" setting.

**Signature:** the time ruler (§4.4). Everything else stays quiet.

## 4. Flow

### 4.1 Three places and one search

- **Today** · **Library** · **Collections**, plus a search button. Phone: a floating dock at the
  bottom, search as a round button beside it. Laptop: one top bar (wordmark, the three places,
  the search field, the account initial). No left rail.
- **Collections** is a hub page with three rows: People, Places (map), Albums. Each row opens
  the existing page. The nav highlights Collections on `/people`, `/map`, `/albums`.
  Calendar stays a view of Library (the Grid · Calendar switch), one tap from the photos.
- **Account menu** (the initial): Settings, Trash, System (admins), Sign out.
- The **Today** tab ships with its own piece (§9). Until then the app opens on Library.

### 4.2 Search is the filter, and the one place to type

One component, `SearchSheet`, replaces the fixed filter column and the `/search` page.

- Opens from the dock button, the top-bar field, `/` or `⌘K`.
- Typing suggests people, places, years, cameras, sources, the existing natural-language
  search, and actions ("Go to System", and with a selection "Add to album…"). Suggestions are
  built in the browser from the facets the app already loads; no new endpoint.
- Each pick becomes a chip. Chips stay visible above the Library grid; × removes one.
- Results are the Library grid itself, filtered. No separate results page.
- "All filters" at the bottom opens the current `FilterPanel` content (date range, guessed
  dates, hidden, sources) as a sheet.
- `/search?q=` redirects into Library with the same chips.
- The sheet reserves a reply area. When the AI chat lands (issue 5), sentences typed here go
  to the model and its proposal appears in that area. Issue 5 is amended: the chat lives in
  this box, not in a separate panel.

Chips live in the page address, so a filtered view can be bookmarked and Back undoes the last
filter. Opening a sheet or a photo adds a history step, so Back on the phone closes it.

### 4.3 Photo view (the loupe)

- Phone: swipe sideways for previous/next, pull down to close, swipe up for details,
  double-tap to favourite. A glass bar at the bottom holds a two-line readout (date · time ·
  place / aperture · shutter · ISO · focal length · file name, in `--font-data`) and five
  actions with icon and label: Favourite, Share, Album, Edit, More.
- Laptop: same bar; details open as a right-hand panel; keyboard shortcuts unchanged.
- Every gesture has a visible button that does the same thing.
- Opening and closing uses a View Transition from the tile where supported, a fade elsewhere.

### 4.4 Time ruler

Replaces `DateScrubber`. A ticked ruler with years in mono and an accent needle showing the
month in view. Phone: horizontal, above the dock, fades when idle. Laptop: vertical on the
right edge. Dragging scrolls the Library; tapping a year jumps.

### 4.5 Selection

Long-press then drag on a phone; click, shift-click, lasso on a laptop (unchanged). The
selection bar becomes a floating pill at the bottom centre: count, Add to album, Share,
Download, Fix date, Delete, and More. `Esc` clears.

**As built in step 3, and what is still open** (plan: `docs/superpowers/plans/2026-10-08-redesign-3-photo-view.md`):

- **Share** is not built, in the photo bar or in the pill: nothing here says what sharing one
  photo does, and handing it to the phone's share sheet sends photo data to other apps.
  Download holds its place (Favourite · Download · Album · Edit · More).
- **Aperture, shutter, ISO and focal length** are not in the API or the database. The
  readout's second line is camera · pixel size · file name until they are.
- The pill says **Move to trash** where this page says Delete: that is what it does, and the
  Trash page keeps "Delete for good" for the other thing.
- The sideways swipe stays in the gesture recogniser (the photo follows the finger through a
  transform), not native snap-scrolling (§6).
- The ruler jumps where a drag ends, not while the finger moves: a far month may need many
  pages. Long-press then drag adds photos to the run; dragging back does not take them out.

### 4.6 System (admin)

`/admin` is named **System** in the UI (route unchanged). Order: one status line ("All good"
or "N things need you"), storage meter, Sources, Working on, Accounts (each with its look,
§5), Backups. Colour appears only on rows that need attention.

## 5. Per-account look

**Who changes what**

- **The admin** sets every account's look from System → Accounts → a person. A form built
  from the field list below, with "Try on my screen" before "Save for Donna".
- **Each account** chooses only its mode (dark / light / follow device) in Settings.
- **Try, then send.** "Try on my screen" applies a sheet to the admin's own screen without
  saving anything; it ends on reload or "Stop trying". "Save for Donna" stores it on her
  account, and her app picks it up the next time it loads or returns to the foreground.
- **Later, via the AI** (issue 5): each account may change its own dials and switches by
  typing a sentence in the search box ("change how this looks" enters a look-editing state).
  While editing, each sentence produces a new sheet that is tried live on their own screen,
  exactly like the admin's "Try on my screen"; a bar offers Keep and Discard, and nothing is
  saved until Keep. Undo afterwards restores the previous sheet. For an admin the same
  action takes a target: "make it warmer with big text" tries it on the admin's screen, then
  "send this to Donna" saves the tried sheet on her account. Only admins may name another
  account; the server checks the role, not the model.
- There is no tweaking screen for non-admins.

**The look sheet**, one JSON object per account:

| Field | Kind | Values | Default |
|---|---|---|---|
| `theme` | theme | `safelight`, `album` (more can ship later) | `safelight` |
| `mode` | mode | `system`, `dark`, `light` | `dark` |
| `accentHue` | dial | 0–360 or null (theme default) | null |
| `corners` | dial | 0–22 px or null | null |
| `photoGap` | dial | 0–8 px or null | null |
| `textScale` | dial | 0.9–1.25 | 1 |
| `thumbSize` | dial | `small`, `medium`, `large` | `medium` |
| `showToday` | switch | true / false | true |
| `startPage` | switch | `today`, `library` | `today` |
| `collectionsRows` | switch | ordered subset of people, places, albums | all three |
| `dockLabels` | switch | true / false | true |

Rules:

- A theme is a named set of token values (dark and light) that ships with the app. A new
  colour palette for someone is a new theme, added in code and checked for contrast once.
  There are no custom colours per account.
- Layout differences are switches from this fixed list. A need no switch covers becomes a
  feature for everyone, plus a switch.
- Unknown fields are rejected, numbers are clamped, a missing or broken sheet falls back to
  the defaults. `showToday: false` forces `startPage: library`. "Reset look" always works.
- The allowed values are defined once, in `backend/.../domain/look.py` (pure), written into
  `docs/contracts/api-v1.md`, and mirrored by hand in `web/src/lib/api/types.ts`.
- Stored as a nullable JSON column `look` on accounts (one migration; null = defaults).
- API: `GET /api/me/look`; `PUT /api/me/look` accepts `mode` only; admins use
  `GET`/`PUT /api/admin/accounts/{id}/look` for the whole sheet.
- The web applies the sheet as a theme attribute plus CSS variables on the root element, and
  caches the last sheet in `localStorage`, read by a small inline script before first paint so
  the default look never flashes. The existing `pa.theme` local setting is migrated into
  `mode` once, then removed.
- All look code sits in `web/src/lib/look/` and `domain/look.py` with no imports from the
  rest of the app, so it can be copied into another project.

As built (step 4, `docs/superpowers/plans/2026-10-08-redesign-4-look-sheet.md`): a value of
the wrong kind or an unknown choice is rejected like an unknown field; `collectionsRows` may
not be empty; dials are whole numbers (text scale: two decimals); every role may set its own
mode; `showToday` and `startPage` are stored but not in the form and without effect until
the Today page exists; `thumbSize` gives the photo size unless one was chosen on the device
in Settings; resetting is a `PUT` of `{}`.

## 6. Technical decisions

- **No component library.** Three primitives of our own on the browser's native dialog and
  popover: `Sheet` (draggable bottom sheet on a phone, panel on a laptop), `Menu`, `Combobox`
  (the search box with chips and suggestions). No new dependency.
- **Gestures:** native snap-scrolling for sideways swiping; one pure recogniser
  (`gesture.ts`) for pull-down, swipe-up and double-tap, unit-tested.
- **Icons:** about 14 inline SVGs in one sprite component. Every icon button keeps the
  accessible name its text button has today.
- **Browsers:** current Safari (iPhone, Mac), Chrome and Firefox. Older versions still work
  with less polish (no blur, no view transitions); no further fallbacks.
- **Doc fix:** `TECH_DECISIONS.md` says the API types are generated from OpenAPI; they are
  hand-written against `docs/contracts/api-v1.md`. The doc is corrected; no switch to
  generation in this work.

## 7. Build order

Split around the open issues: issues 3–9 add screens, so the foundation goes first and the
regrouping goes last.

**Part A — now** (new issue: "Redesign foundation"):

1. Tokens, fonts, shared control styles, icon set, primitives; `DESIGN_PRINCIPLES.md` and
   `TECH_DECISIONS.md` updated. Pure restyle. **Acceptance: every existing end-to-end test
   passes without being edited** (one exception: the page colour hard-coded in `web/e2e/fixes.spec.ts`).
2. Shell: dock and top bar replace `Nav`, account menu. Old pages stay reachable (People,
   Places, Albums listed on a plain Collections page; Calendar stays in Library).
3. Photo view, selection pill, time ruler.
4. Look sheet: migration, domain validation, API, mode switch in Settings, per-account form
   in System.

**Part B — last** (issue 10, "Simplify the interface"):

5. Search sheet replaces the filter column and `/search`.
6. Collections hub with content strips.
7. System page regrouped around whatever issues 3–9 added.

Each step is one or more PRs under 400 lines, leaves the app working and passes `just check`.

## 8. Tests

- Look validation: defaults, each bound, clamping, unknown field, broken JSON, null
  overrides, `showToday`/`startPage` rule, member may change `mode` only, admin any account.
- Applying a sheet: variables and theme attribute set, reset restores defaults, `pa.theme`
  migration, cached sheet applied before paint.
- Primitives: keyboard and focus behaviour of `Sheet`, `Menu`, `Combobox`; axe clean.
- Gesture recogniser: thresholds for each gesture, diagonal and cancelled drags.
- Search sheet: chips add/remove filters, `/search?q=` redirect, actions only with a selection.
- Nav: Collections highlighted on its child routes; Library highlighted on `/calendar`; System hidden for non-admins; switches
  hide Today and reorder Collections rows.
- Photo view: each gesture and its button reach the same state; shortcuts still work.
- Perf test still meets the scroll budget with glass on.
- Screenshots (desktop + phone, dark and light, Safelight) regenerated from synthetic
  fixtures. No automatic screenshot comparison yet. The Album theme is checked by eye.

## 9. Not in this piece

- **Today and heroes** (own spec, next): the Today page, "On this day", weekly picks and
  themed sets from a scheduled job, "Keep as album". First step is "On this day" alone.
- **AI chat** itself (issue 5). This spec only reserves its place in the search box and
  defines the look sheet it will fill.
- Print themes, native apps, custom colours per account.
