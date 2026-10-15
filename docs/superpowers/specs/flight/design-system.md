# photoManager — design system (target direction "Flight")

Self-hosted family photo library (SvelteKit). Audience: C and C's partner, an iPhone user who
already likes Apple Photos. Mobile first, laptop second. Goal: feel like Apple Photos built by
the Tesla/SpaceX product-design team — content first, cinematic, quiet chrome, fast.

## Product context

Places (main navigation): **Home** (a story: Rediscover "N years ago", On this day, Years),
**Library** (justified photo grid by month with a time ruler, filter chips), **Collections**
(rows: People faces, Places covers, Albums covers, Utilities tiles), **Search**, **You**
(avatar → settings, look, admin). A photo opens the **Loupe** (full-screen viewer, swipe between
photos, Details sheet, edit, share, favourite). Jobs: relive memories together, find a photo
fast, curate albums, print.

## Principles

1. **Photos are the interface.** Edge to edge, never rounded in grids, true aspect ratios
   (justified rows), 2 px gutters. Hero photos may bleed to the screen edge with a soft
   bottom scrim for type.
2. **Chrome floats and recedes.** All bars are glass over content; no solid grey header strips,
   no borders, no 1 px lines. Chrome fades or shrinks on scroll.
3. **No dead space.** Every hero is full-bleed or fills its row; text sits *on* the photo
   (bottom-left over scrim) or in a deliberate column — never floating next to nothing.
4. **One accent, used sparingly.** Selection and focus only.
5. **Motion is physics.** Everything that moves follows the finger and settles on a spring;
   only `transform` and `opacity` animate; 60/120 fps or it does not ship.

## Colour (dark is the default and the hero mode)

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#000000` (true black; OLED) | page; photos sit on it |
| `--raised` | `#111214` | sheets, menus, dialogs |
| `--fill` | `#1C1D20` | chips, fields, segmented, sheet rows |
| `--ink` | `#F5F5F7` | text, primary button fill |
| `--ink-2` | `#A1A1A6` | secondary text |
| `--ink-3` | `#6E6E73` | disabled / decoration |
| `--glass` | `rgb(22 22 24 / 0.62)` + `blur(24px) saturate(1.8)` | floating bars, dock, top bar, viewer chrome |
| `--glass-edge` | inner highlight `inset 0 0 0 0.5px rgb(255 255 255 / 0.12)` | the only "edge" glass gets |
| `--scrim-photo` | `linear-gradient(to top, rgb(0 0 0 / .72), transparent 55%)` | under type set on a photo |
| `--accent` | `oklch(0.82 0.14 72)` safelight amber | selection + focus only |
| `--scrim` | `rgb(0 0 0 / 0.6)` | behind sheets |
| `--lift` | `0 20px 60px rgb(0 0 0 / 0.5)` | menus, toasts |

Light mode: `--bg #F5F5F7`, `--raised #FFFFFF`, `--ink #1D1D1F`, `--ink-2 #636366` (contrast ≥ 4.5:1 on fills), glass
`rgb(255 255 255 / 0.7)`.

## Type

One grotesk family for the whole UI: **Inter** (variable, OFL, self-hosted; optical sizes via
`Inter Display` cut for ≥ 28 px). Atkinson Hyperlegible Next stays available as the "Larger
text" accessibility face. No serif in the default look.

| Token | Size / weight / tracking | Role |
| --- | --- | --- |
| `--fs-display` | 56 px / 700 / -0.03em (phone 40 px) | hero titles on photos ("Seven years ago") |
| `--fs-34` | 34 px / 700 / -0.022em | large page titles (iOS large title) |
| `--fs-22` | 22 px / 650 / -0.015em | section titles ("Rediscover", "Years") |
| `--fs-17` | 17 px / 500 | body, buttons |
| `--fs-15` | 15 px / 500 | interface |
| `--fs-13` | 13 px / 500 | metadata, dates, counts (tabular) |
| `--fs-11-caps` | 11 px / 600 / +0.08em uppercase | the one SpaceX touch: tiny eyebrow labels above hero titles ("ON THIS DAY · 2019"), sparingly |

Numbers are tabular. Hierarchy by size + weight, then `--ink-2`.

## Space & shape

4 px base: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 96. Page side padding: 32 px laptop,
16 px phone; hero content bleeds past it. Max content width: none for photo grids; 1440 px for
Home rails. Radii: controls 14 px, sheets/cards 28 px (continuous-corner feel), pills full.
Photos in grids: 0 radius. Hero/memory cards on Home: 24 px radius allowed (they are cards,
not grid photos).

## Components

- **Top bar (laptop)**: floating glass capsule, 52 px tall, centred, 16 px from top, holding
  the places as icon + word with a sliding lens on the active one; search is a round glass
  button that expands into a field; avatar at far right as its own glass circle. Bar hides on
  scroll down, returns on scroll up.
- **Dock (phone)**: floating glass capsule at the bottom, 64 px, places icon-over-word, sliding
  lens; search as a separate round glass button beside it (iOS 26 style).
- **Hero memory card**: full-width (laptop: full content width, 21:9 to 16:9; phone: edge to
  edge, 4:5), photo fills it, scrim at bottom, eyebrow caps label + display title + date set
  bottom-left on the photo, a glass play button bottom-right. Slow Ken Burns drift (transform).
- **Rails**: horizontal snap-scrolling rows of 4:5 cards (phone) / 3:2 cards (laptop) with
  title on photo; peek of the next card at the edge.
- **Year tiles**: big tabular year numeral on the photo ("2019") — Tesla-style spec number.
- **Chips / segmented / fields / buttons**: glass or `--fill` pills, 36 px tall (44 touch),
  primary = ink fill, black text.
- **Sheets**: rise on spring, grab handle, 28 px top radius, glass background over scrim.
- **Loupe (viewer)**: true black, photo fit, chrome (top: close/date/place; bottom: actions) is
  glass and fades out on tap. Horizontal paging is a 3-slot carousel tracking the finger 1:1
  with rubber-band at ends and spring settle; swipe down to dismiss back to the grid tile
  (shared-element zoom).

## Motion

- Spring for everything gestural: stiffness 300–400, damping ~30 (iOS default feel).
- Press: scale 0.96, 100 ms. Fades 200 ms `cubic-bezier(.2,0,0,1)`. Sheets 380 ms
  `cubic-bezier(.32,.72,0,1)`.
- Page changes: view transitions (push/pop slide, places cross-fade); photo open/close is a
  shared-element zoom from/to its tile.
- Only `transform` and `opacity`; respect `prefers-reduced-motion`.
