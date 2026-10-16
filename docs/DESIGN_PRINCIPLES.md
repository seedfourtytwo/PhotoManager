# Design principles

The look is **Flight**: Apple Photos as the Tesla/SpaceX product team would build it. Content
first, cinematic, quiet chrome, fast. In a photo app **the photos are the data**: the chrome
floats over them as glass and recedes, and nothing else competes for the eye. Charts and
comparisons still follow Edward Tufte (rules 5–7).

## 1. Rules

1. **Maximise photo ink.** Photos use as much of the screen as possible. In a grid a photo has
   no card, shadow, rounded corner or gradient, and the gutters are 2 px. Home's hero and
   memory cards are cards, not grid photos: they may take `--r-card` corners and carry
   `--scrim-photo` under the words set on them.
2. **Never crop without consent.** Grids are _justified_ (true aspect ratios). Crops only exist
   inside album frames, chosen by the user. A panorama or a tall strip (wider than 4:1,
   narrower than 0.4:1) gets a tile of that limit and sits whole inside it, never stretched.
3. **Erase non-data ink.** No borders and no 1 px lines: groups separate by space, rows inside
   a group by a 2 px seam (`--fine`). The only gradient is `--scrim-photo`, under words set on a
   photo. Tracking (letter-spacing) only through the `--track-*` tokens; capitals only through
   `.eyebrow`, a tiny label above a hero title, used sparingly. A dot, a
   label or a sentence that has no job goes. An action everyone knows (select, share, close,
   more…) is its icon alone, named for screen readers and as a tooltip; words stay in the main
   navigation, in menus and wherever the action is not obvious.
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
9. **Motion follows the hand, and never stutters.** A gesture ends on a spring
   (`lib/spring.ts`) seeded with the speed the finger let go at, never on a fixed duration.
   Presses 100 ms, fades ≤ 240 ms; sheets and page changes up to 380 ms on the sheet curve.
   Sheets and the photo view move with the finger; everything else moves only to show where
   something went. Only `transform` and `opacity`
   animate (the compositor draws them): never size, layout or blur. Respect
   `prefers-reduced-motion`.
10. **Same thing, same place.** Laptop and phone share the information architecture; only the
    layout adapts.

## 2. Character, tokens and components

**Character: Flight.** Photos sit on a true black page (dark, the default; on an OLED phone
the screen is simply off around them) or a soft paper page (light). Everything you read or
operate, dates, counts and camera settings included, speaks in one grotesk, **Inter**; weight
and size make the hierarchy. One accent — **safelight amber** — marks selection and focus and
nothing else. Chrome floats over the photos as one glass recipe and recedes. This is the
**Safelight** theme; the earlier serif look
lives on as the **Album** theme (serif titles, small corners, indigo ink). A theme changes
colours, corners and the title face, never layout.

**Each account has its own look** (`docs/adr/0001`): a theme, a mode (dark, light, or like
the device), a few dials and a few switches, kept as a validated sheet of values and never as
CSS. The account chooses its mode and what its Home shows on You; an admin sets the rest in
Admin → People → Look.
The dials only move tokens (`--acc-h`, `--r-1`/`--r-2`, `--gutter`, the root text size); the
switches choose from fixed lists (which Collections rows, which Home blocks, words under the
dock icons). So the
rules on this page hold for every look: any accent hue passes contrast because lightness and
chroma stay the theme's, and "reset look" always works. The tables below give a theme's own
values, which is what a dial left alone uses.

The `.data` class marks counts and dates (same face, figures lined up) so they can be found and
restyled in one place. The `--ok` / `--fail` colours exist; the System page's status dots are not built
yet (issue #10), so the checklist items about them apply once they are.

The sources of truth are `web/src/lib/themes.css` (colour), `fonts.css` (typefaces) and
`tokens.css` (everything else); the tables below mirror them for Safelight. The rules that use
the tokens are beside them, one file per subject and all imported by `tokens.css`: `base.css`
(elements), `buttons.css`, `fields.css`, `utilities.css` (small shared classes, glass, transitions).

### Colour

| Token                          | Dark (default)                   | Light                     | Use                                                                                                                                                 |
| ------------------------------ | -------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--bg`                         | #000000 (true black)             | #F5F5F7                   | the page; photos sit on it                                                                                                                          |
| `--raised`                     | #111214                          | #FFFFFF                   | dialogs, sheets, menus, toasts                                                                                                                      |
| `--ink`                        | #F5F5F7                          | #1D1D1F                   | text, primary button fill, chart ink                                                                                                                |
| `--ink-2`                      | #A1A1A6                          | #636366                   | secondary text, quiet controls                                                                                                                      |
| `--ink-3`                      | #6E6E73                          | #8E8E93                   | disabled text and decoration only                                                                                                                   |
| `--hairline`                   | #1C1D20                          | #E8E8ED                   | the placeholder of a photo tile still loading; never a line                                                                                         |
| `--fill`                       | #1C1D20                          | #E8E8ED                   | chips, fields, segmented controls, and the rows of a sheet                                                                                          |
| `--lens`                       | ink at 14 %                      | same                      | the chosen tab or segment                                                                                                                           |
| `--lift`                       | 0 20 px 60 px black at 50 %      | a soft grey shadow        | what floats: menus, toasts, dialogs, the laptop capsule                                                                                             |
| `--tint`                       | ink at 7 %                       | ink at 6 %                | hover wash; field fill                                                                                                                              |
| `--accent`                     | oklch(0.82 0.14 72)              | oklch(0.50 0.15 72)       | selection and focus only                                                                                                                            |
| `--on-accent`                  | #17110A                          | #FFFFFF                   | text and the check mark on the accent                                                                                                               |
| `--glass`                      | raised at 62 % + `--blur`        | same                      | the one glass recipe: the capsule, the dock, bars over photos, sheets                                                                               |
| `--glass-edge`                 | inset 0.5 px white at 12 %       | inset 0.5 px black at 6 % | the only edge glass gets; nothing else draws a hairline                                                                                             |
| `--ok` / `--fail`              | #7BD3A0 / #FF7A6B                | #1F7A4A / #B3261E         | status dots on the System page only                                                                                                                 |
| `--scrim`                      | black at 60 %                    | cool grey 38 %            | behind dialogs and sheets                                                                                                                           |
| `--scrim-photo`                | black at 72 % fading out by 55 % | same                      | the one gradient: under words set on a photo (hero titles, eyebrows)                                                                                |
| `--on-photo` / `--on-photo-90` | #FFFFFF / white at 90 %          | same                      | marks drawn on a photo: the selection circle, the favourite mark, the crop handles / the crop frame                                                 |
| `--photo-shade-55`             | black at 55 %                    | same                      | the shade that keeps those marks readable on any photo: inside the empty selection circle, behind the favourite mark and over what a crop cuts away |

Light `--ink-2` is #636366, not Apple's #6E6E73: that one is 4.15:1 on a fill and fails the
4.5:1 below.

`themes.spec.ts` checks every theme in both modes: text ≥ 7:1, secondary text and status
colours ≥ 4.5:1, white on the darkest stop of `--scrim-photo` ≥ 4.5:1, and the accent ≥ 4.5:1
at every hue (its lightness is fixed per mode, only
the hue may vary per account). Separation is by value, never by hue. Status colours exist
only on the System page; everywhere else, something that needs attention gets full ink.

### Type

Three families, self-hosted under `web/static/fonts` (SIL OFL; nothing fetched at runtime):

- **Inter** (variable, weight 100–900 and optical size 14–32) — `--font-ui`, `--font-title`
  and `--font-data`: everything you read or operate, titles (weight 700) and data. Optical
  sizing is on for the whole page, so text at 32 px and up takes Inter's Display shapes.
  Tabular numerals are on globally. Descriptions and opening lines use the title face at
  weight 400 in `--voice-style` (upright; italic in the Album theme).
- **Atkinson Hyperlegible Next** (variable, 200–800) — `--font-large`: the Larger text face,
  drawn by the Braille Institute for readers with low vision. Declared but not in the default
  look; an account will choose it once the look sheet has a face (a backend change of its own).
- **Newsreader** — `--font-serif`: the Album theme's title and voice face only.

A terminal command or a path an admin reads uses the system's monospace (`--font-code`).
Text is letter-spaced only through the `--track-*` tokens (tighter on large titles) and set in
capitals only by `.eyebrow`; small capitals never (`style-guard.spec.ts` checks).

| Token           | Size / weight / tracking               | Role                                                                                       |
| --------------- | -------------------------------------- | ------------------------------------------------------------------------------------------ |
| `--fs-11`       | 11 px / 600 / +0.08em, `.eyebrow` only | the tiny capital label above a hero title ("ON THIS DAY · 2019"), sparingly                |
| `--fs-13`       | 13 px / 500                            | metadata, dates, counts, group labels, captions under thumbnails                           |
| `--fs-15`       | 15 px / 500                            | interface text (the base)                                                                  |
| `--fs-17`       | 17 px / 500                            | reading text, buttons                                                                      |
| `--field-phone` | 16 px, in pixels on purpose            | every field on a phone (no zoom-on-focus); grows with the look's text dial, never under 16 |
| `--fs-22`       | 22 px / 650 / −0.015em                 | section titles, month and year headings, dialog titles                                     |
| `--fs-34`       | 34 px / 700 / −0.022em                 | page titles (`h1`, the iOS large title)                                                    |
| `--fs-display`  | 56 px, phone 40 px / 700 / −0.03em     | display: hero titles on photos, album and person titles, Welcome / sign-in                 |

The old names (`--fs-12` … `--fs-40`) stay as aliases of the nearest new size while the screens
move over, then go.

The sizes are in rem and the root is the browser's own text size (16 px unless the reader set
another) times the look's text dial, so at the dial's 100 % a token renders at the pixels in
these tables: interface text 15, small text 13, a page title 34, `--s-4` 16
(`e2e/type.spec.ts` measures them). At 125 % everything in rem is a quarter larger; what is
promised in pixels (`--target`, `--dock`, `--top`, the corners) stays.

Line heights: `--lh-display` 1.05 (display), `--lh-tight` 1.15 (titles), `--lh-ui` 1.45
(interface), `--lh-text` 1.6 (prose, max `--measure` 36 rem). Group labels (`h3`, `legend`) are
13 px / 600 / `--ink-2`, sentence case; eyebrow capitals only above a hero title. A count goes under or beside its title in `--ink-2`, never boxed or dotted.

### Space, shape, motion

| Token                                     | Value                                                                                                                                                      |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--s-1 … --s-9`                           | 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 96 px — the only spacings used                                                                                       |
| `--page-x`                                | 32 px laptop, 16 px phone (grids on a phone use `--gutter` and pad their words; a hero bleeds past it)                                                     |
| `--gutter`                                | 2 px between photos, and beside them on a phone; the look's gap dial moves it (0–8 px), so nothing else uses it                                            |
| `--fine`                                  | 2 px: the finest line and gap inside a control (the ruler's needle, an icon and its word) and the seam between rows of a group; no dial moves it           |
| `--r-1` / `--r-2` / `--r-pill`            | 14 px controls · 28 px sheets and raised surfaces · full round for bars and chips; grid photos are never rounded (a face is a round badge, not a photo)     |
| `--r-card`                                | 24 px (`--r-2` less 4, so the corners dial moves it): Home's hero and memory cards                                                                         |
| `--check-radius`                          | 4 px: checkbox corners (`--r-1` would make a 16 px box round)                                                                                              |
| `--target`                                | 44 px, in pixels on purpose: minimum control height on touch screens (`pointer: coarse`) and the smallest size of any phone button                         |
| `--capsule`                               | 52 px: the height of the laptop's floating glass capsule                                                                                                   |
| `--top`                                   | the room the capsule takes on a laptop (16 px above it, 8 px below); 0 on a phone                                                                          |
| `--dock`                                  | 64 px: the floating dock on a phone, and the photo view's action bar                                                                                       |
| `--bar`                                   | `--dock` + 16 px: the room a phone page keeps free at its bottom so nothing hides under the dock                                                           |
| `--pill`                                  | 52 px: the least height of the selection pill; the toast steps over it by this much                                                                        |
| `--blur`                                  | `blur(24px) saturate(1.8)`: the frosted-glass look (with `--glass` and `--glass-edge`; solid where blur is unavailable or `prefers-reduced-transparency`)  |
| `--margin`                                | 224 px (14rem) right margin for notes on a laptop                                                                                                          |
| `--press` / `--motion` / `--motion-sheet` | 100 ms a control giving under the finger · 200 ms fades and colour · 380 ms sheets and page changes; off under `prefers-reduced-motion`                    |
| `--ease` / `--ease-sheet`                 | `cubic-bezier(.2,0,0,1)` · `cubic-bezier(.32,.72,0,1)`, the curve of an iPhone sheet                                                                       |
| `--ease-spring` / `lib/spring.ts`         | a spring (stiffness 300, damping 30) as a CSS `linear()` curve, and the same spring in code for gestures, seeded with the release speed                    |

Layers, lowest first (a number of 1 to 5 inside one component orders its own pieces and is
not a token):

| Token                    | Value | What                                                                 |
| ------------------------ | ----- | -------------------------------------------------------------------- |
| `--z-ruler`              | 4     | the time ruler beside the photos                                     |
| `--z-bar`                | 20    | the floating capsule on a laptop                                     |
| `--z-selection`          | 25    | the selection pill                                                   |
| `--z-dock`               | 28    | the dock on a phone (over the pill, so its open menu is not covered) |
| `--z-menu` / `--z-lasso` | 30    | an open menu / the rectangle drawn while selecting with the mouse    |
| `--z-loupe`              | 50    | the photo view                                                       |
| `--z-toast`              | 60    | the toast                                                            |
| `--z-editor`             | 70    | the editor, over the photo view it opens from                        |
| `--z-skip`               | 100   | the skip link, when focused                                          |

### Component rules

- **Buttons** are words when the action needs saying. Default: no box, `--tint` wash on hover
  (pointer devices only). **`.primary`** — the one action a dialog or form exists for — is
  filled with `--ink` (never the accent), 600 weight. Every control gives a little under the
  finger (scale 0.95, `--press`).
- **Icon buttons** (`ui/IconButton`, `.icon-button`): an action everyone knows, as its icon
  alone; round, 44 px, named by `label` (accessible name and tooltip). `filled` puts it on a
  `--fill` disc when it stands on the page. Its word shows under it when the root carries
  `data-words="all"` (the later Larger text mode) or when `worded` is set.
- **Chips** (`ui/Chip`, `.chip`): a question asked of the photos (a filter) or a suggestion.
  Pill, `--fill`; once answered it shows the answer in ink with an × that clears it.
- **Segmented** (`ui/Segmented`): a few choices side by side (Grid / Calendar, Dark / Light);
  the chosen one sits under `--lens`.
- **Tile groups** (`ui/TileGroup`, `ui/TileRow`, `.tiles`, `.tile-row`): settings, admin,
  utilities and a sheet's lists. Rows are tiles (icon, title, one quiet line, a value, a
  chevron when it opens something) on a rounded group, separated by a `--fine` seam; on a
  sheet they take `--fill`. A red `.attention-dot` marks what needs an admin.
- **Switches**: a checkbox with `role="switch"`, drawn as a sliding knob; on is ink.
- **Fields** are a soft box (`--fill`, `--r-1`) that takes a 2 px inset accent ring on focus.
  Labels sit above (`.field`), 12 px. Selects keep the native chevron. A date is typed or
  pasted into a text field (`DateField`) that shows it day first on the 24-hour clock; the
  browser's own date control is not used, because it follows the browser's language.
- **Checkboxes and radios** are drawn (2 px `--ink-2` outline, `--check-radius` corners;
  checked = ink fill with a `--bg` check / inner ring), so both themes match. `.choice` lays an
  option out in a row.
- **Sliders**: a 4 px `--fill` track, a small ink thumb; larger thumb on touch.
- **Dialogs** are sheets: glass over `--scrim`, `--r-2` (28 px) corners, rising on a spring; a title; actions bottom
  right, Cancel left of the primary. On a phone every dialog, a filter question and the loupe's
  details become **bottom sheets**, as wide as the screen, with rounded top corners, a grab handle and
  safe-area padding; they rise on the sheet curve and follow the finger down from the handle or
  the title, closing when let go far or fast enough (`lib/sheet-drag.ts`). A dialog, the photo
  editor and a filter sheet each add a history step (`lib/history-step.ts`), so Back closes
  them; what was chosen in a filter sheet stays.
  So does the photo's Details sheet on a phone (`lib/info-sheet.svelte.ts`): Back closes the
  sheet, the next Back the photo; on a laptop Details is a panel beside the photo, with no step.
  The editor with changes that are not saved asks first, whichever way it is left (Back,
  Escape, Cancel): "Keep editing" or "Discard changes". With nothing changed it just closes.
- **Menus** (`Menu`): a button that opens a small raised sheet of 44 px rows, links and actions
  together. Escape or a press outside closes it.
- **Navigation** (`Nav`): the places (`PLACES` in `lib/nav.ts`) and Search, nothing else. On a
  phone a floating glass capsule holds the places, icon over word, the chosen one under a
  `--lens` that slides to it (transform only; gone on a page that is no place), with Search a
  round glass button beside it; the look's "dock labels" switch takes the words off the screen,
  not from screen readers. On a laptop the same language at the top: a floating glass capsule
  (`--capsule`, 52 px, 16 px from the top, centred) holding the places as icon and word under
  the sliding lens, Search a round glass button beside it and the avatar its own glass circle
  at the far right. It hides while the page scrolls down and comes back on any scroll up, at
  the top of the page and while anything in it has focus. No wordmark, no account menu.
- **The avatar** (`Avatar`): the person's initial, opening You. On a phone it sits at the right
  of each page's title row (`PageHead`); on a laptop beside the capsule. An admin sees a red dot on
  it while something needs them, and its name says what in one sentence. Members never see
  backup state; there is no banner.
- **Page changes** are view transitions of the page area alone (`movePage` in `lib/motion.ts`,
  `pageMove` in `lib/nav.ts`): a page opened from this one slides in from the right, Back
  slides it out to the right, another place of the bar cross-fades; the bars stay still. Not
  when only the query or the photo changes, not after the browser's own swipe back, not under
  reduced motion. A tap made while the page slides is not taken, as on an iPhone.
- **Toasts**: one line on a raised slip, bottom centre, the action (Undo) as a bold word. It
  steps over the selection pill and a phone's lying ruler. In the photo view the bottom is the
  bar's, so it sits under Close and Info; it is always on top of an open dialog and inside it,
  where a screen reader still hears it.
- **The Home Screen tip** (`InstallTip`): once per phone, and only in a browser tab, a glass
  card rises over the photos above the dock: the app's icon, "Make Photos an app" and how. An
  iPhone is told ⋯, then Share, then Add to Home Screen; an Android phone gets Install, the
  browser's own prompt, which comes over HTTPS only. × puts it away for good on that device.
  It steps over the selection pill and the lying ruler as the toast does. Never on a laptop or
  a tablet, never in the app opened from the Home Screen (`lib/install-tip.ts` decides).
- **Selection**: the circle that chooses a photo is a 2 px white ring round a shade, so it
  reads on any photo; chosen, it is a filled accent circle with a check and the photo takes a
  3 px accent frame inside its edge. The actions come to the photos as a floating glass pill at
  the bottom centre: × (stop) first, then "3 selected" with only the number in the accent, then
  icons named by their words: Add to album, Share where the device has a share sheet and up
  to ten photos are chosen (else Download), Move to trash, and More for the rest (Select all,
  Fix date, Download, Favourite, Hide, Make private, and "Download all" of a filtered
  Library). Select in the Library's head brings the pill before a photo is chosen; then a tap
  chooses. What does not fit (a narrow phone, large text, a long count) joins More: nothing
  leaves the glass. Escape clears.
- **Filters** are a row of chips under the Library's title, the same on a phone and a laptop:
  Who (once the server filters by person), When, Where, Favourites, Camera, More, then
  "Clear all" when two or more are set. Favourites toggles where it is; each of the others asks
  one question in a sheet (a bottom sheet on a phone, a popover under its chip on a laptop),
  counted under the other filters. A set chip shows its answer ("July 2019", "Lisbon",
  "Phone, Old hard disk") in ink with an × that clears that question. Words to search for
  that come with a link show as one more chip. The address keeps every filter.
- **Focus**: 2 px accent outline, 2 px offset (inset on photo tiles).
- **Icons**: a set of 2 px-stroke SVGs on a 24 grid drawn for this app (`lib/icons.ts`), one
  component, no icon font. In the main navigation an icon carries its word; elsewhere an
  icon button stands alone (see Icon buttons). Every icon button has the accessible name of
  the action.
- **Glass** (`.glass`): one recipe, `--glass` behind a `--blur` with a `--glass-edge`, for what
  floats over photos (the capsule, dock, photo actions, selection, time ruler) and for sheets
  over their scrim. It turns solid `--raised` where blur is unavailable, under
  "reduce transparency", or if it costs the 60 fps scroll budget. Glass is the rule and solid
  the exception: the stylesheet asks `(prefers-reduced-transparency: reduce)` and never its
  negation, because Safari does not know the question and would then show no glass at all.
- **The look form** (Admin → People → Look): one control per field of the sheet, each with
  its range or its choices, so nothing can be entered that the server would refuse. Home has
  two: Show Home (off takes Home out of the dock) and Opens on (Home or Library; without Home
  only Library, so the choice is off); its blocks and their order are an order of one's own,
  as are the Collections rows. "Try on
  my screen" shows the sheet on the admin's own screen and saves nothing; while it runs, one
  quiet line at the top of every page says whose look is being tried and offers Stop trying.
- **Collections rows** show what is behind them, not a sentence about it: people as round
  faces with a name and no count, places as 4:3 covers and albums as a grid of 4:3 covers
  (a chosen frame, so it may crop), each with a plain number (the word "photos" is for screen
  readers). Named people come first, then the album changed last, then the places with the
  most photos; a country that is one city and nothing else is shown once, as the city. A row
  holds eight; its heading, with a chevron, opens the whole of it, and Albums has its + on
  that line. On a phone a strip runs off the side and scrolls; on a laptop it wraps. A row with
  nothing in it says in one quiet line what will be there. Under the rows, **Utilities** is a
  tile group: To review, Hidden (the Library showing only hidden photos) and Trash, each with
  its count.
- **A person and an album** open like a chapter, the title in display size (`--fs-display`) under
  the page head's Back: a person's centred round portrait (its own tool for who may change it)
  and "27 photos, 2012 to 2026", their photos grouped by year; an album's cover (full width on
  a phone, beside the title on a laptop) and "12 photos, July 2024", then Add photos (a sheet
  that picks from the Library) and Share. Everything else (Rename, Change portrait, Merge
  with…, Hide; Download, Print, Arrange, Delete album) waits behind the round ⋯ (`Menu`
  `round`); a destructive row is in `--fail`.
- **Trash and To review**: one sentence under the title. Trash: Select and ⋯ (Restore all,
  Empty trash, confirmed) in the head, and each photo's days left as a small label on a photo
  shade (`PhotoGrid` `note`). To review: grouped by reason as tiles, one decision per group
  (Keep all, Move all to trash); a photo on its own opens from its tile.
- **Search**: the field first, a pill with its magnifier; before anything is typed, faces,
  places as chips and, once search by meaning is set up, things as chips.
- **Sign-in**: who is looking is a row of round badges with each person's initial, the name
  under it. The PIN shows as four dots, never as a text box. A touch screen gets a number pad
  of round keys (1 to 9, then 0 with the word Delete to its right), set in the middle of the
  screen where the thumb is, and no system keyboard; a laptop has no pad and types. The
  fourth digit signs in; a wrong PIN empties the dots, which shake once, and says why.
- **The whole screen of a phone** is the page's (`viewport-fit=cover`): photos and glass run
  under the clock, the notch and the home bar, and nothing to read or press does. Every fixed
  or sticky piece adds the device's own inset (`env(safe-area-inset-*)`) on the side it
  touches, on both sides when the phone lies on its side; `--top` is that inset on a phone.
  Opened from an iPhone's Home Screen the page runs under the status bar too, the clock written
  over it in white (`black-translucent` in `app.html`).
- **Words for whoever is reading**: a terminal command and a folder path are for an admin, on
  the Admin page. Anyone else reads what it means for them ("New faces are not being found
  yet"); an admin reading the same note is also told where to set it up. A photo's details
  say which folder it came from and what the file is called; only an admin reads the path.
- **A dialog opens on the few choices most people want**, each with one quiet line saying what
  you get (Download: Full size, Smaller, and With edits when there are edits). Formats,
  pixel sizes and file naming wait under "More options"; picking a plain choice again wins.
- **Empty states** (`.empty-state`): one title-face sentence saying what is (not) here, then a
  plain sentence saying what to do, with a link where there is one.
- **You** (`/settings`, from the avatar): Back to where it was opened from (the history's, so
  that page keeps its scroll), the initial large with the name and role, then tile groups:
  Look (Dark · Light · Like the device, a segmented control), Home shows, in this order (an
  order of one's own, while Home is in the dock), Needs you (admins, only when
  something does: the dot and its sentence, leading to it), Admin (admins), Phones that send
  photos here (each phone a tile that opens its sheet: what it keeps, Leave out screenshots,
  Send everything again, Revoke; + adds one), Account (Change PIN in a sheet, Sign out).
- **Admin** puts status first: three tiles, Backups (the red dot and one plain sentence),
  Library (photos and free space, and the work running) and Problems (a count). Then Folders,
  Search and faces and People as tile groups, their + (and Check all) on the label line. A
  tile opens a sheet: its actions as icon cards over their words, its details below; paths,
  commands and run tables live only there. Backups and Problems open from their tiles; a
  backup place shows its state as a dot in `--ok` or `--fail` with a shape that reads without
  colour.
- **The photo view** (the loupe) gives the photo the whole screen. Its chrome floats over it as
  glass: round icon buttons at the top, Close (a chevron down) at the left and Zoom, Full screen
  (laptop) and Details at the right; one bar at the bottom with a two-line readout in the UI
  face, its pieces set apart by space, never by dots (the day in words, the time, the place /
  the camera, aperture, shutter, ISO and focal length; a piece that does not fit is left out
  whole, a long place or camera is cut), and at most five icon actions: Favourite, Download,
  Add to album, Edit, More. A screen reader hears each line in words. On a device with a share
  sheet (a phone over HTTPS) Share takes Download's place and Download is under More; where
  there is none, Share is not shown. The heart is the Favourite button, first in the bar: the
  accent and filled when on, with a short pop when pressed. The details are label and value
  tiles (Taken, Place, Camera, Settings, From with the photo's name and, for an admin, the
  file's path, People, Albums): a panel beside the photo on a laptop and a bottom sheet on a
  phone. Chrome fades when idle. The photo follows the finger; every gesture (swipe sideways,
  pull down, swipe up, double-tap) has a button that does the same. A double tap zooms in on
  the spot tapped and the next one goes back; two fingers zoom from the photo's fit up to four
  times its size. Zoomed in, the chrome is put away, one finger moves the photo as far as its
  edges, and it is not swiped; another photo opens at its fit. It opens from its tile and
  closes back to it as a view transition.
- **An order of one's own** (`ui/OrderList`: Collections rows, Home blocks): a tile group,
  each row a switch, the ones shown first in their order with a Move up icon (the first has
  none), then the ones switched off. The last one shown cannot be switched off. A row moves to
  its new place (transform only; a jump under reduced motion).
- **Home** reads top to bottom like a story, and a block shows only when it has photos: the
  date ("Wednesday 14 October") with the avatar; On this day, its cover full width at its own
  shape (a tall one stops short of the screen, whole), a display title in plain words ("Three
  years ago today", "A year ago this week") and one line of where and with whom; Rediscover, a
  dozen photos from across the years, the first large like On this day ("Ten years ago", the
  day and the place) and playing the dozen, the rest a justified block (so with no On this day
  Home still opens on a large photo); Memories, a sideways row of 3:4 covers with title and
  dates; Years, a row of square covers of one size (small multiples) with the year and its
  count, each playing its year, the heading opening the Library; Pinned, the account's own
  photos as a justified block ("Choose" opens the Library, where a photo's More and the selection's More
  pin and unpin); People, faces with names; New this week, one sentence ("42 photos arrived
  from Léa's iPhone") over the newest photos. A cover or a memory plays (a round play mark on
  it); a photo opens the photo view and steps through its block. While Home is asked for, the
  room of a cover and a row stays quiet (no spinner). With nothing to show, one sentence says
  so and what to do. Home is where a session opens, unless the look says Library: only the
  first page of a tab after signing in moves there, and a page asked for (a link) is never
  moved. **Home goes on into the Library**: past Home's last block the Library follows on the
  same page (its large title on the black, no line, then its filters and its timeline), so it
  can be reached by scrolling. Once its title passes under the top, the lens moves to Library
  and the address becomes `/` without a page change or a history step; back up, both return
  to Home. Library (or any plain link to it) pressed on Home scrolls there, and Home scrolls
  back to the top. A bare `/` stays the Library on its own, so the Library never waits for
  Home; without Home in the dock nothing goes on (lib/continuation.svelte.ts).
- **The story player** plays a memory full screen over everything (a modal dialog in the top
  layer): about forty photos spread over the period, each whole for 3.2 s while it is pushed
  in slowly and the next fades in over it (transform and opacity only; the next two are
  fetched ahead). Progress is a row of segments at the top, the running one filling as a
  `scaleX` animation. The title and dates sit on glass at the bottom; × and Pause are round
  glass buttons at the top. Tap the right two thirds for the next photo, the left third for
  the previous; the arrow keys do the same. A finger held down pauses it, a pull down follows
  the finger and closes it past the sheet's threshold; ×, Escape and Back close it too. It
  stands still while the page is hidden. Next after the last photo ends it. Reduced motion:
  plain cuts, no push-in. No music yet.
- **The time ruler** is the one signature: even 2 px ticks for the months (drawn, never a
  gradient), the years in the interface face, and the needle as a filled accent pill naming
  the month in view. Upright at the right edge on a laptop; lying above the dock on a phone,
  where it shows while the page scrolls and fades when idle. A drag moves the needle and the
  Library jumps where it is let go; a tap on a year jumps to it. Month headings say the month
  and nothing else; on a phone they stick under the compact title.
- **Charts** (year bars, calendar, map) use `--ink` only, zero-based, directly labelled; a
  chosen year bar is in full ink, the others lighter. The calendar heat map draws each day's
  ink by its count, with no stroke; the day under the pointer or the keyboard takes the
  accent. The chosen map dot takes the accent because it is the selection.

## 3. Layout by device

|                 | Laptop (≥ 1024 px)                                              | Phone (< 640 px)                                                                                                                  |
| --------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Navigation      | floating glass capsule: the places; Search and the avatar beside | floating glass capsule with the places under a sliding lens, Search a round button beside it; the avatar in each page's title row |
| Filters         | a row of chips under the title; a question opens under its chip | the same chips; a question opens as a bottom sheet                                                                                |
| Loupe metadata  | Details: a panel of label/value tiles beside the photo          | Details opens a bottom sheet of the same tiles                                                                                    |
| Loupe actions   | round Close and Details at the top, one glass bar at the bottom | the same                                                                                                                          |
| Time ruler      | upright at the right edge                                       | lying above the dock, fading when idle                                                                                            |
| Selection       | click / shift-click / drag-lasso                                | long-press, then drag or tap                                                                                                      |
| Grid row height | ~220 px                                                         | ~110 px, pinch to change                                                                                                          |

The row heights are for the look's medium photo size; small is ¾ of it and large 1.4 times.
Only the look sets it: there is no photo size setting per device.

## 4. Print design (albums)

- Generous margins, consistent baseline for captions, one serif family per theme.
- Layouts are a small, well-made set rather than infinite freedom.
- Every page has a bleed-aware safe area; nothing important within 5 mm of trim.
- Captions are text, never baked into the image.

## 5. Review checklist (tick in PR)

- [ ] Could any border, box or shadow be removed without losing meaning? Does every icon in a bar have its word?
- [ ] Does the chrome recede on scroll? Does every gesture settle on a spring, never a fixed duration?
- [ ] Are photos shown at true aspect ratio (unless in a user-chosen album frame)?
- [ ] Is the accent colour used only for selection/focus?
- [ ] Charts: zero-based, directly labelled, no chartjunk?
- [ ] Works at 375 px wide and at 1440 px wide?
- [ ] Keyboard reachable, visible focus, AA contrast, reduced motion respected?
- [ ] Only tokens: no raw colours, sizes or spacings outside `tokens.css`, `themes.css`, `fonts.css` and the shared rules `tokens.css` imports?
- [ ] Phone: 44 px targets, nothing wraps to a second toolbar line, safe areas respected?
- [ ] Checked in both themes, and with the look's dials at their ends (text size 125 %, corners 0 and 22, gap 0 and 8)?
