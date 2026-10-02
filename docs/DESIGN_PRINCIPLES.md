# Design principles

Inspired by Edward Tufte. In a photo app **the photos are the data**. Everything that is not a
photo — chrome, borders, badges, backgrounds — is non-data ink to be reduced until removing
more would hurt understanding.

## 1. Rules

1. **Maximise photo ink.** Photos use as much of the screen as possible; no cards, drop shadows,
   rounded frames or gradients around them. Gutters are 2–4 px.
2. **Never crop without consent.** Grids are *justified* (true aspect ratios). Crops only exist
   inside album frames, chosen by the user.
3. **Erase non-data ink.** No borders where whitespace works; no icon when a word is clearer;
   one hairline (1 px, low-contrast) is the strongest divider we use.
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
9. **Motion only to explain.** Transitions ≤ 150 ms, used to show where something went
   (photo zooms into loupe). Respect `prefers-reduced-motion`.
10. **Same thing, same place.** Laptop and phone share the information architecture; only the
    layout adapts.

## 2. Character, tokens and components

**Character: a family album, typeset.** Photos sit on a deep graphite page (dark, the default
for viewing) or on a quiet paper page (light). Titles, dates, places and captions speak in a
serif with optical sizes — the album's handwriting, typeset; the interface speaks in a small,
plain sans. One accent, **indigo ink** (the fountain-pen ink once used to write under prints),
marks selection and focus and nothing else. The one bold gesture is typographic: display-size
serif titles on albums, people and the front door; everything else stays quiet and dense.

The source of truth is `web/src/lib/tokens.css`; this table mirrors it.

### Colour

| Token | Dark (default) | Light | Use |
|---|---|---|---|
| `--bg` | #181817 | #F5F4F0 | the page; photos sit on it |
| `--raised` | #222120 | #FCFBF8 | dialogs, sheets, menus, toasts |
| `--ink` | #ECEAE4 | #1F1E1B | text, primary button fill, chart ink |
| `--ink-2` | #A6A39C (7.1:1) | #625F58 (5.8:1) | secondary text, quiet controls |
| `--ink-3` | #7A7772 | #8C8981 | disabled text and decoration only — never text that must be read |
| `--hairline` | #302F2C | #DCD9D1 | the strongest divider; empty calendar days; tile placeholder |
| `--tint` | ink at 7 % | ink at 6 % | hover / pressed wash on quiet controls |
| `--accent` | #A9B0FF (8.8:1) | #3B40B0 (7.5:1) | selection and focus only |
| `--on-accent` | #181817 | #FFFFFF | the check mark on a selected photo |
| `--scrim` | near-black 66 % | warm grey 38 % | behind dialogs and sheets |

Contrast ratios are against `--bg`; all text pairs pass WCAG AA (most AAA). Separation is by
value, never by hue: there is no red, green or yellow status colour. Something that needs
attention gets full ink and a 2 px ink rule beside it.

### Type

Two families, both self-hosted under `web/static/fonts` (SIL OFL; nothing fetched at runtime):

- **Newsreader** (variable, optical sizes, roman + italic) — `--font-text`: page, section,
  month and year titles; album and person names; dates and places in the loupe; the search
  line; the "Photos" wordmark (italic).
- **Instrument Sans** (variable) — `--font-ui`: everything you operate. Tabular numerals are on
  globally (`font-variant-numeric: tabular-nums`).
- `--font-mono` (system) only for paths, repositories and tokens.

| Token | Size | Role |
|---|---|---|
| `--fs-12` | 12 px | metadata, counts, group labels, captions under thumbnails |
| `--fs-14` | 14 px | interface text (the base) |
| `--fs-16` | 16 px | reading text; every field on a phone (no zoom-on-focus) |
| `--fs-20` | 20 px | serif section titles, month and year headings, dialog titles |
| `--fs-28` | 28 px | serif page titles (`h1`) |
| `--fs-40` | 40 px | display: album and person titles, Welcome / sign-in |

Line heights: `--lh-tight` 1.15 (titles), `--lh-ui` 1.45 (interface), `--lh-text` 1.6 (prose,
max `--measure` 36 rem). Group labels (`h3`, `legend`) are 12 px / 600 / `--ink-2`, **sentence
case** — no uppercase tracking. A count beside a serif title is set in the sans at 12 px.

### Space, shape, motion

| Token | Value |
|---|---|
| `--s-1 … --s-8` | 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 px — the only spacings used |
| `--page-x` | 24 px laptop, 12 px phone (grids on a phone use `--gutter` and pad their words) |
| `--gutter` | 3 px between photos |
| `--r-1` / `--r-2` | 3 px controls · 8 px raised surfaces; photos are never rounded |
| `--target` | 44 px: minimum control height on touch screens (`pointer: coarse`) |
| `--rail` / `--margin` / `--bar` | 120 px rail · 256 px right margin · 56 px phone bar |
| `--motion` / `--ease` | 120 ms, `cubic-bezier(.2,0,0,1)`; off under `prefers-reduced-motion` |

### Component rules

- **Buttons** are words. Default: no box, `--tint` wash on hover (pointer devices only). Quiet
  actions in a toolbar are `--ink-2` and turn `--ink` on hover. **`.primary`** — the one action
  a dialog or form exists for — is filled with `--ink` (never the accent), 600 weight. Pressed
  toggles (Info, Arrange, crop ratio, Grid/Calendar) are underlined, not filled.
- **Fields** are a line to write on: a hairline underneath that turns `--accent` on focus. Labels
  sit above (`.field`), 12 px. Selects keep the native chevron.
- **Checkboxes and radios** are drawn (1.5 px `--ink-2` outline; checked = ink fill with a
  `--bg` check / inner ring), so both themes match. `.choice` lays an option out in a row.
- **Sliders**: hairline track, small ink thumb; larger thumb on touch.
- **Dialogs** are `--raised` with an 8 px radius over `--scrim`; serif title; actions bottom
  right, Cancel left of the primary. On a phone every dialog, the filters and the loupe's info
  become **bottom sheets** with rounded top corners and safe-area padding.
- **Menus** ("More" in the nav and the selection bar) are small raised sheets of 44 px rows.
- **Toasts**: one line on a raised slip, bottom centre, the action (Undo) as a bold word.
- **Selection**: a 3 px accent frame inset on the photo (with a 1 px shade so it reads on any
  photo) and a filled accent circle with a check; the count in the selection bar is the only
  accent text.
- **Focus**: 2 px accent outline, 2 px offset (inset on photo tiles).
- **Icons**: words first. The few marks — previous/next chevrons, the favourite heart, the
  check, the search-clear cross — are inline 1.5 px-stroke SVGs drawn for this app. No icon font.
- **Empty states** (`.empty-state`): one serif sentence saying what is (not) here, then a plain
  sentence saying what to do, with a link where there is one.
- **Section headers** in Settings sit in the left margin (book margin heads); Admin sections
  are a serif title with their actions on the same baseline, separated by one hairline.
- **The loupe** draws nothing over the photo: one band of words above it (Close … actions …
  Info), the sidenote in the right margin on a laptop; on a phone Close/Info at the top and the
  photo actions in a single-line bar at the bottom, in thumb reach. Chrome fades when idle.
- **Charts** (year bars, calendar, map) use `--ink` only, zero-based, directly labelled; the
  chosen map dot takes the accent because it is the selection.

## 3. Layout by device

| | Laptop (≥ 1024 px) | Phone (< 640 px) |
|---|---|---|
| Navigation | slim left rail: Library · Map · People · Albums · Search | bottom bar, same 5 items |
| Filters | right margin, always visible, collapsible | bottom sheet |
| Loupe metadata | right margin "sidenote" | Info opens a bottom sheet |
| Loupe actions | one band above the photo | Close/Info on top, actions in a bottom bar |
| Selection | click / shift-click / drag-lasso | long-press then tap |
| Grid row height | ~220 px | ~110 px, pinch to change |

## 4. Print design (albums)

- Generous margins, consistent baseline for captions, one serif family per theme.
- Layouts are a small, well-made set rather than infinite freedom.
- Every page has a bleed-aware safe area; nothing important within 5 mm of trim.
- Captions are text, never baked into the image.

## 5. Review checklist (tick in PR)

- [ ] Could any border, box, shadow or icon be removed without losing meaning?
- [ ] Are photos shown at true aspect ratio (unless in a user-chosen album frame)?
- [ ] Is the accent colour used only for selection/focus?
- [ ] Charts: zero-based, directly labelled, no chartjunk?
- [ ] Works at 375 px wide and at 1440 px wide?
- [ ] Keyboard reachable, visible focus, AA contrast, reduced motion respected?
- [ ] Only tokens: no raw colours, sizes or spacings outside `tokens.css`?
- [ ] Phone: 44 px targets, nothing wraps to a second toolbar line, safe areas respected?
- [ ] Checked in both themes?
