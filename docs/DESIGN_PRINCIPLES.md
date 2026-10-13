# Design principles

Inspired by Edward Tufte. In a photo app **the photos are the data**. Everything that is not a
photo — chrome, borders, badges, backgrounds — is non-data ink to be reduced until removing
more would hurt understanding.

## 1. Rules

1. **Maximise photo ink.** Photos use as much of the screen as possible; no cards, drop shadows,
   rounded frames or gradients around them. Gutters are 2–4 px.
2. **Never crop without consent.** Grids are *justified* (true aspect ratios). Crops only exist
   inside album frames, chosen by the user. A panorama or a tall strip (wider than 4:1,
   narrower than 0.4:1) gets a tile of that limit and sits whole inside it, never stretched.
3. **Erase non-data ink.** No borders where whitespace works; one hairline (1 px, low-contrast)
   is the strongest divider on a page. Navigation and action bars use a small drawn icon
   **with** its word; an icon never stands alone where a word fits.
4. **Data density with calm.** Show a lot, quietly: many thumbnails, small type for metadata,
   one accent colour used only for selection and focus.
5. **Small multiples over dashboards.** Comparisons (years, places, people) are shown as
   repeated, identically scaled small panels — never mismatched charts.
6. **Charts are honest.** Zero-based scales for counts; no 3D, no pie charts, no dual axes;
   direct labels instead of legends; the calendar heat map uses one sequential hue.
7. **Words are part of the graphic.** Dates, places and names sit next to what they describe
   (margin notes, like Tufte's sidenotes), not in tooltips only.
8. **Layering and separation by value, not colour.** Secondary information is lighter grey,
   not a different colour.
9. **Motion follows the hand.** Transitions ≤ 240 ms. Sheets and the photo view move with the
   finger; everything else moves only to show where something went. Respect
   `prefers-reduced-motion`.
10. **Same thing, same place.** Laptop and phone share the information architecture; only the
    layout adapts.

## 2. Character, tokens and components

**Character: a darkroom, with camera data on the readouts.** Photos sit on a near-black page
(dark, the default) or a cool paper page (light). Everything you read or operate speaks in one
sans; dates, counts and camera settings speak in a monospace, like the figures in a viewfinder.
One accent — **safelight amber** — marks selection and focus and nothing else. Bars that sit
over photos are translucent glass. This is the **Safelight** theme; the earlier serif look
lives on as the **Album** theme (serif titles, small corners, indigo ink). A theme changes
colours, corners and the title face, never layout.

**Each account has its own look** (`docs/adr/0001`): a theme, a mode (dark, light, or like
the device), a few dials and a few switches, kept as a validated sheet of values and never as
CSS. The account chooses its mode in Settings; an admin sets the rest in Admin → People → Look.
The dials only move tokens (`--acc-h`, `--r-1`/`--r-2`, `--gutter`, the root text size); the
switches choose from fixed lists (which Collections rows, words under the dock icons). So the
rules on this page hold for every look: any accent hue passes contrast because lightness and
chroma stay the theme's, and "reset look" always works. The tables below give a theme's own
values, which is what a dial left alone uses.

The `.data` class (mono for counts and dates) exists and is used on the account menu's
counts and badge; other counts and dates outside the photo view take it as their screens are
reworked. The `--ok` / `--fail` colours exist; the System page's status dots are not built
yet (issue #10), so the checklist items about them apply once they are.

The sources of truth are `web/src/lib/themes.css` (colour), `fonts.css` (typefaces) and
`tokens.css` (everything else); the tables below mirror them for Safelight. The rules that use
the tokens are beside them, one file per subject and all imported by `tokens.css`: `base.css`
(elements), `buttons.css`, `fields.css`, `utilities.css` (small shared classes, glass, transitions).

### Colour

| Token | Dark (default) | Light | Use |
|---|---|---|---|
| `--bg` | #0D0F12 | #F2F3F5 | the page; photos sit on it |
| `--raised` | #171A1F | #FFFFFF | dialogs, sheets, menus, toasts, bars |
| `--ink` | #F1F2F4 | #14161A | text, primary button fill, chart ink |
| `--ink-2` | #A3A9B3 | #565D68 | secondary text, quiet controls |
| `--ink-3` | #6B717C | #8A909A | disabled text and decoration only |
| `--hairline` | #262A31 | #DCDFE4 | the strongest divider; tile placeholder |
| `--tint` | ink at 7 % | ink at 6 % | hover wash; field fill |
| `--accent` | oklch(0.82 0.14 72) | oklch(0.50 0.15 72) | selection and focus only |
| `--on-accent` | #17110A | #FFFFFF | text and the check mark on the accent |
| `--glass` | raised at 74 % + blur | same | floating bars over photos |
| `--ok` / `--fail` | #7BD3A0 / #FF7A6B | #1F7A4A / #B3261E | status dots on the System page only |
| `--scrim` | near-black 66 % | cool grey 38 % | behind dialogs and sheets |
| `--on-photo` / `--on-photo-90` | #FFFFFF / white at 90 % | same | marks drawn on a photo: the selection circle, the favourite mark, the crop handles / the crop frame |
| `--photo-shade-18` / `-20` / `-25` / `-55` | black at 18 · 20 · 25 · 55 % | same | the shade that keeps those marks readable on any photo: inside the empty selection circle · the hairline round it · the hairline inside the selection frame · behind the favourite mark and over what a crop cuts away |

`themes.spec.ts` checks every theme in both modes: text ≥ 7:1, secondary text and status
colours ≥ 4.5:1, and the accent ≥ 4.5:1 at every hue (its lightness is fixed per mode, only
the hue may vary per account). Separation is by value, never by hue. Status colours exist
only on the System page; everywhere else, something that needs attention gets full ink.

### Type

Three families, all self-hosted under `web/static/fonts` (SIL OFL; nothing fetched at runtime):

- **Hanken Grotesk** (variable) — `--font-ui`: everything you read or operate, and titles
  (`--font-title`, weight 720, tight tracking). Tabular numerals are on globally. Descriptions
  and opening lines use the title face at weight 400 in `--voice-style` (upright; italic in
  the Album theme).
- **Martian Mono** (variable, set at 80 % width) — `--font-data`, class `.data`: dates, counts,
  camera settings, file names, paths, system status. Never a control, never a sentence.
- **Newsreader** — `--font-serif`: the Album theme's title and voice face only.

| Token | Size | Role |
|---|---|---|
| `--fs-12` | 12 px | metadata, counts, group labels, captions under thumbnails |
| `--fs-14` | 14 px | interface text (the base) |
| `--fs-16` | 16 px | reading text |
| `--field-phone` | 16 px, in pixels on purpose | every field on a phone (no zoom-on-focus); grows with the look's text dial, never under 16 |
| `--fs-20` | 20 px | section titles, month and year headings, dialog titles |
| `--fs-28` | 28 px | page titles (`h1`) |
| `--fs-40` | 40 px | display: album and person titles, Welcome / sign-in |

Line heights: `--lh-tight` 1.15 (titles), `--lh-ui` 1.45 (interface), `--lh-text` 1.6 (prose,
max `--measure` 36 rem). Group labels (`h3`, `legend`) are 12 px / 600 / `--ink-2`, **sentence
case** — no uppercase tracking. A count beside a title is set in the data face at 12 px.

### Space, shape, motion

| Token | Value |
|---|---|
| `--s-1 … --s-8` | 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 px — the only spacings used |
| `--page-x` | 24 px laptop, 12 px phone (grids on a phone use `--gutter` and pad their words) |
| `--gutter` | 2 px between photos, and beside them on a phone; the look's gap dial moves it (0–8 px), so nothing else uses it |
| `--fine` | 2 px: the finest line and gap inside a control (the ruler's needle, an icon and its word); no dial moves it |
| `--r-1` / `--r-2` / `--r-pill` | 12 px controls · 20 px raised surfaces · full round for bars and chips; photos are never rounded (a person's face is a round badge, not a photo) |
| `--check-radius` | 4 px: checkbox corners (`--r-1` would make a 16 px box round) |
| `--target` | 44 px, in pixels on purpose: minimum control height on touch screens (`pointer: coarse`) and the smallest size of any phone button |
| `--top` | 56 px top bar on a laptop; 0 on a phone. Everything sticky offsets by it |
| `--dock` | 56 px: the floating dock on a phone, and the photo view's action bar |
| `--bar` | `--dock` + 16 px: the room a phone page keeps free at its bottom so nothing hides under the dock |
| `--pill` | 52 px: the least height of the selection pill; the toast steps over it by this much |
| `--blur` | `blur(18px) saturate(1.4)`: the frosted-glass look of bars over photos (with `--glass`; solid where blur is unavailable or `prefers-reduced-transparency`) |
| `--margin` | 224 px (16rem) right margin for notes and filters on a laptop |
| `--motion` / `--motion-sheet` / `--ease` | 200 ms · 240 ms for sheets · `cubic-bezier(.2,0,0,1)`; off under `prefers-reduced-motion` |

Layers, lowest first (a number of 1 to 5 inside one component orders its own pieces and is
not a token):

| Token | Value | What |
|---|---|---|
| `--z-ruler` | 4 | the time ruler beside the photos |
| `--z-bar` | 20 | the top bar on a laptop |
| `--z-selection` | 25 | the selection pill |
| `--z-dock` | 28 | the dock on a phone (over the pill, so its open menu is not covered) |
| `--z-menu` / `--z-lasso` | 30 | an open menu / the rectangle drawn while selecting with the mouse |
| `--z-sheet-backdrop` / `--z-sheet` | 35 / 40 | the filter sheet on a phone and the scrim under it |
| `--z-loupe` | 50 | the photo view |
| `--z-toast` | 60 | the toast |
| `--z-editor` | 70 | the editor, over the photo view it opens from |
| `--z-skip` | 100 | the skip link, when focused |

### Component rules

- **Buttons** are words. Default: no box, `--tint` wash on hover (pointer devices only). Quiet
  actions in a toolbar are `--ink-2` and turn `--ink` on hover. **`.primary`** — the one action
  a dialog or form exists for — is filled with `--ink` (never the accent), 600 weight. Pressed
  toggles (Info, Arrange, crop ratio, Grid/Calendar) are underlined, not filled.
- **Fields** are a soft box (`--tint` fill, `--r-1`) that takes an accent border on focus.
  Labels sit above (`.field`), 12 px. Selects keep the native chevron.
- **Checkboxes and radios** are drawn (1.5 px `--ink-2` outline, `--check-radius` corners;
  checked = ink fill with a `--bg` check / inner ring), so both themes match. `.choice` lays an
  option out in a row.
- **Sliders**: hairline track, small ink thumb; larger thumb on touch.
- **Dialogs** are `--raised` with an `--r-2` radius over `--scrim`; a title; actions bottom
  right, Cancel left of the primary. On a phone every dialog, the filters and the loupe's info
  become **bottom sheets**, as wide as the screen, with rounded top corners and safe-area
  padding. A dialog, the photo editor and the filter sheet each add a history step
  (`lib/history-step.ts`), so Back closes them; what was chosen in the filter sheet stays.
- **Menus** (`Menu`): a button that opens a small raised sheet of 44 px rows, links and actions
  together. Escape or a press outside closes it. The account button shows the person's initial;
  a count that needs attention sits on it in full ink, never the accent.
- **Toasts**: one line on a raised slip, bottom centre, the action (Undo) as a bold word. It
  steps over the selection pill and a phone's lying ruler. In the photo view the bottom is the
  bar's, so it sits under Close and Info; it is always on top of an open dialog and inside it,
  where a screen reader still hears it.
- **Selection**: a 3 px accent frame inset on the photo (with a 1 px shade so it reads on any
  photo) and a filled accent circle with a check. The actions come to the photos as a floating
  glass pill at the bottom centre: the count (the only accent text), Add to album, Download,
  Fix date, Move to trash, and More for the rest. What does not fit beside the count and Clear
  (a narrow phone, large text, a long count) joins More: nothing leaves the glass. Escape clears.
- **Focus**: 2 px accent outline, 2 px offset (inset on photo tiles).
- **Icons**: a small set of 1.6 px-stroke SVGs drawn for this app, one component, no icon
  font. In navigation and action bars an icon carries its word beneath or beside it. Every
  icon button has the accessible name of the action.
- **Glass** (`.glass`): only for bars that float over photos (dock, top bar, photo actions,
  selection, time ruler). It turns solid `--raised` where blur is unavailable, under
  "reduce transparency", or if it costs the 60 fps scroll budget. Glass is the rule and solid
  the exception: the stylesheet asks `(prefers-reduced-transparency: reduce)` and never its
  negation, because Safari does not know the question and would then show no glass at all.
- **The look form** (Admin → People → Look): one control per field of the sheet, each with
  its range or its choices, so nothing can be entered that the server would refuse. The
  exceptions are `showToday` and `startPage`: they have no control until the Today page
  exists. "Try on
  my screen" shows the sheet on the admin's own screen and saves nothing; while it runs, one
  quiet line at the top of every page says whose look is being tried and offers Stop trying.
- **Collections rows** show what is behind them, not a sentence about it: people as round
  faces with a name, albums and places as 4:3 covers (a chosen frame, so it may crop), each
  with its count. Named people come first, then the album changed last, then the places with
  the most photos; a country that is one city and nothing else is shown once, as the city. A
  row holds eight; its heading, with a small arrowhead, opens the whole of it. On a phone the
  strip runs off the side and scrolls; on a laptop it wraps. A row with nothing in it says in
  one quiet line what will be there.
- **Sign-in**: who is looking is a row of round badges with each person's initial, the name
  under it. The PIN shows as four dots, never as a text box. A touch screen gets a number pad
  of round keys (1 to 9, then 0 with the word Delete to its right), set in the middle of the
  screen where the thumb is, and no system keyboard; a laptop has no pad and types. The
  fourth digit signs in; a wrong PIN empties the dots, which shake once, and says why.
- **The whole screen of a phone** is the page's (`viewport-fit=cover`): photos and glass run
  under the clock, the notch and the home bar, and nothing to read or press does. Every fixed
  or sticky piece adds the device's own inset (`env(safe-area-inset-*)`) on the side it
  touches, on both sides when the phone lies on its side; `--top` is that inset on a phone.
- **Words for whoever is reading**: a terminal command and a folder path are for an admin, on
  the Admin page. Anyone else reads what it means for them ("New faces are not being found
  yet"); an admin reading the same note is also told where to set it up. A photo's details
  say which folder it came from and what the file is called; only an admin reads the path.
- **A dialog opens on the few choices most people want**, each with one quiet line saying what
  you get (Download: Full size, Smaller, and With edits when there are edits). Formats,
  pixel sizes and file naming wait under "More options"; picking a plain choice again wins.
- **Empty states** (`.empty-state`): one title-face sentence saying what is (not) here, then a
  plain sentence saying what to do, with a link where there is one.
- **Section headers** in Settings sit in the left margin (book margin heads); Admin sections
  are a title with their actions on the same baseline, separated by one hairline.
- **The photo view** (the loupe) gives the photo the whole screen. Its chrome floats over it as
  glass: Close and Info as pills at the top, one bar at the bottom with a two-line readout in
  the data face (date · time · place / camera · size · file name) and at most five actions,
  each an icon over its word: Favourite, Download, Album, Edit, More. The details are the
  sidenote in the right margin on a laptop and a bottom sheet on a phone. Chrome fades when
  idle. The photo follows the finger; every gesture (swipe sideways, pull down, swipe up,
  double-tap) has a button that does the same. It opens from its tile and closes back to it as
  a view transition.
- **The time ruler** is the one signature: even ticks for the months, the years in the data
  face, an accent needle with the month in view. Upright at the right edge on a laptop; lying
  above the dock on a phone, where it shows while the page scrolls and fades when idle. A drag
  moves the needle and the Library jumps where it is let go; a tap on a year jumps to it.
- **Charts** (year bars, calendar, map) use `--ink` only, zero-based, directly labelled; the
  chosen map dot takes the accent because it is the selection.

## 3. Layout by device

| | Laptop (≥ 1024 px) | Phone (< 640 px) |
|---|---|---|
| Navigation | glass top bar: Library · Collections · Search · the account button | floating glass dock: Library · Collections, with Search and the account button as round buttons beside it |
| Filters | right margin, always visible, collapsible | bottom sheet |
| Loupe metadata | right margin "sidenote" | Info opens a bottom sheet |
| Loupe actions | Close and Info at the top, one glass bar at the bottom | the same |
| Time ruler | upright at the right edge | lying above the dock, fading when idle |
| Selection | click / shift-click / drag-lasso | long-press, then drag or tap |
| Grid row height | ~220 px | ~110 px, pinch to change |

## 4. Print design (albums)

- Generous margins, consistent baseline for captions, one serif family per theme.
- Layouts are a small, well-made set rather than infinite freedom.
- Every page has a bleed-aware safe area; nothing important within 5 mm of trim.
- Captions are text, never baked into the image.

## 5. Review checklist (tick in PR)

- [ ] Could any border, box or shadow be removed without losing meaning? Does every icon in a bar have its word?
- [ ] Are photos shown at true aspect ratio (unless in a user-chosen album frame)?
- [ ] Is the accent colour used only for selection/focus?
- [ ] Charts: zero-based, directly labelled, no chartjunk?
- [ ] Works at 375 px wide and at 1440 px wide?
- [ ] Keyboard reachable, visible focus, AA contrast, reduced motion respected?
- [ ] Only tokens: no raw colours, sizes or spacings outside `tokens.css`, `themes.css`, `fonts.css` and the shared rules `tokens.css` imports?
- [ ] Phone: 44 px targets, nothing wraps to a second toolbar line, safe areas respected?
- [ ] Checked in both themes, and with the look's dials at their ends (text size 125 %, corners 0 and 22, gap 0 and 8)?
