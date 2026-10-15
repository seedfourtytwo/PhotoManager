# Flight: foundations audit and migration plan

Audited 2026-10-15 against this worktree (b17c52a) plus `origin/main` 780fa34 (PR #82) for the
shell files. Target: `../design-system.md`. Read-only: no app code changed.

## 1. Guards that block Flight

Each one changes on purpose, in the slice named in §6. Contrast guards stay; Flight's values pass
them, with one light-mode fix (see §3).

| Guard (file) | Exact rule today | Blocks | New rule |
| --- | --- | --- | --- |
| `style-guard.spec.ts` "no text is letter-spaced or set in capitals" | regex `letter-spacing:\s*([^;}]+)` (anything but `0`/`normal`) \| `text-transform:\s*uppercase` \| `font-variant(-caps)?:…(small\|all)-caps` → offenders must be `[]` | negative display tracking, the `ON THIS DAY · 2019` eyebrow | **Allowlist.** `letter-spacing` may only be `var(--track-*)`, and the `--track-*` values are declared only in `tokens.css`. `text-transform: uppercase` appears only in `utilities.css` `.eyebrow`. small/all-caps stay banned. Second test: `.eyebrow` font-size token is `--fs-11` in rem, so the text dial still scales it |
| `style-guard.spec.ts` "every font family ships its licence" | `toEqual(['AtkinsonHyperlegibleNext-OFL.txt','Newsreader-OFL.txt'])` | Inter | add `'Inter-OFL.txt'` (sorted) |
| `style-guard.spec.ts` "every font file is used…" | woff2 in `static/fonts` == `url()`s in `fonts.css` | none; it catches a missing or unused Inter file | keep |
| `style-guard.spec.ts` "browser chrome colours equal the Safelight dark page colour", "favicon sits on the page colour" | `<meta theme-color>` in `+layout.svelte`, `manifest.webmanifest`, `favicon.svg` fill == `:root --bg` | needs `#000000` in 3 files | keep the rule; change the values. `+layout.svelte` `content="#0d0f12"` → `#000000` (shell file, see §5) |
| `style-guard.spec.ts` "no stylesheet draws a 1 px line" | `(border…\|outline\|box-shadow):[^;}]*\b1px\b` | not `--glass-edge` (`0.5px` doesn't match `\b1px\b`) | keep. Add: an inset hairline appears only as `var(--glass-edge)`, so the 0.5 px edge can't spread to other components. On a 1x screen 0.5 px draws as 1 px; accept that or drop the edge there with `@media (resolution < 2x)` |
| `style-guard.spec.ts` `--gutter`, reduced-transparency, non-empty, banned names | — | none | keep |
| `tokens.spec.ts` "uses the Safelight shape by default" | `--r-1:'12px'`, `--r-2:'20px'`, `--gutter:'2px'`, `--motion:'200ms'`, `--motion-sheet:'380ms'`, `--press:'120ms'`, `--ease-sheet` | 14 / 28 radii, press 100 ms | `--r-1:'14px'`, `--r-2:'28px'`, `--press:'100ms'`, plus new `--r-card`, `--ease-spring` |
| `tokens.spec.ts` "keeps the Album theme small-cornered" | `--r-1:'3px'`, `--r-2:'8px'`, `--gutter:'3px'` | none | keep (the Album theme keeps its character) |
| `tokens.spec.ts` "holds no colour of its own" | no `#hex`/`rgb(` in `tokens.css :root` | Flight's literal `--glass`, `--glass-edge`, `--scrim-photo` | keep. Put the literals in `themes.css` (per variant), or derive them with `color-mix` (see §3) |
| `tokens.spec.ts` "reads and shows data in the same face" | `--font-ui` matches `/^'Atkinson Hyperlegible Next'/`; `--font-data` = `var(--font-ui)` | Inter | `/^'Inter'/`, and `--font-data` stays `var(--font-ui)`. New test: `--font-large` (Atkinson) is defined |
| `tokens.spec.ts` "the root text size" | `--fs-16:'1rem'`; `html` font-size `calc(var(--fs-16) * var(--text-scale, 1))`; `--margin:'14rem'` | renaming the scale removes `--fs-16` | new `--root: 1rem` token; `html` = `calc(var(--root) * var(--text-scale, 1))`. Same promise: the reader's own size × the dial, never px |
| `tokens.spec.ts` glass ×3 | `.glass` uses `var(--glass)` + `var(--blur)`, solid `var(--raised)` fallback | none | keep. Add `box-shadow: var(--glass-edge)` to the `@supports` block's expected rules |
| `themes.spec.ts` contrast | per variant: `--ink`/`--bg` ≥ 7, `--ink-2`/`--bg` ≥ 4.5, ok/fail ≥ 4.5, `--ink`/`--fill` ≥ 7, `--ink-2`/`--fill` ≥ 4.5, accent at 24 hues vs `--bg` and `--on-accent` ≥ 4.5 | Flight's light `--ink-2 #6E6E73` on any `--fill` near `#E8E8ED` = 4.15 (**fails**) | keep every threshold. Use light `--ink-2 #636366` (5.5 on bg, 4.9 on `#E8E8ED`). Add `--glass-edge` and `--scrim-photo` to `COLOURS`. New check: `--on-photo` on the darkest stop of `--scrim-photo` ≥ 4.5 (eyebrow/titles on photos) |
| `themes.spec.ts` "contains nothing but theme blocks" | only the 6 selectors | none | keep. A `data-face` block goes in `fonts.css`/`tokens.css`, not `themes.css` |
| `e2e/type.spec.ts` "type and space render at the sizes the design table states" | html 16; tile line 14 (`--fs-14`); `.small` 12; h1 28; `--s-5` margin 24; sheet h2 20 | new scale | html 16; tile line 15; `.small` 13; h1 34; margin 24; sheet h2 22 |
| `e2e/type.spec.ts` "text dial multiplies the table" | h1 35 @125 %, 25.2 @90 % | — | 42.5 @125 %, 30.6 @90 % |
| `e2e/type.spec.ts` phone fields ≥ 16 px | `--field-phone` | none | keep (17 px body already clears it) |
| `e2e/exposure.spec.ts:46,131`, `ruler.spec.ts:65`, `loupe.spec.ts:299` | `toHaveCSS('font-family', /Atkinson Hyperlegible Next/)` | Inter | `/^"?Inter/`. Better: share one helper, `UI_FACE` in `e2e/helpers.ts`, so the next change touches one line |
| `e2e/look.spec.ts:104,106` | body bg `rgb(242, 243, 245)` light / `rgb(13, 15, 18)` dark | new colours | `rgb(245, 245, 247)` / `rgb(0, 0, 0)` |
| `e2e/look.spec.ts:256` corners 0 → button radius `0px`; `actions.spec.ts:340` pill `999px` | — | none | keep |
| `look/apply.spec.ts`, `boot.spec.ts` | `THEMES_OWN.safelight.corners` == CSS `--r-1`; `app.html` first-paint script == `rootLook` | changing radii | update together: corners 12→14, `SURFACE_PER_CONTROL` 5/3→2 (14→28), `app.html` `(corners * 5) / 3` → `corners * 2` |

Missing guard worth adding (slice 1): **photos never rounded** with the corners dial at 22.
Grid tiles (`PhotoGrid`, `JustifiedGrid`), Loupe image and album covers all report computed
`border-radius: 0px`. Today this rests on hand-written `border-radius: 0` in 11 places.

## 2. Docs

### `docs/DESIGN_PRINCIPLES.md`

| Rewrite | Line(s) | Why / new wording |
| --- | --- | --- |
| Intro "Inspired by Edward Tufte… non-data ink" | 3-5 | New framing: "Apple Photos built by the Tesla/SpaceX product team: content first, chrome floats and recedes." Keep Tufte only for charts (§1.5-6) |
| §1.1 "no cards, drop shadows, rounded frames or gradients" | 9-10 | Grid photos: still none. Home hero and memory cards may be rounded `--r-card` and carry `--scrim-photo` |
| §1.3 "No gradients, no letter-spacing, no capitals" | 14-15 | Gradients only as `--scrim-photo` under type on a photo. Tracking only via `--track-*`. Capitals only in `.eyebrow`, sparingly |
| §1.9 motion "Presses and fades ≤ 240 ms…" | 29-33 | Gestures settle on a spring (`lib/spring.ts`, seeded with release velocity); presses 100 ms; the rest unchanged |
| §2 "Character: a darkroom… near-black page… one face drawn for readers with low vision" | 39-44 | True black (OLED). Inter for the UI, Atkinson as the Larger text face. Keep "theme changes colours, corners, title face, never layout" |
| §2 colour table | 64-84 | Replace with the §3 values; add `--glass-edge`, `--scrim-photo` |
| §2 Type: "Two families… Atkinson… `--font-ui`, `--font-title`, `--font-data`" + "never letter-spaced and never set in capitals" | 93-103 | Three families: Inter (UI, data), Atkinson (Larger text), Newsreader (Album). Tracking and eyebrow rule as in §1 |
| §2 type table `--fs-12…--fs-40` and the "interface 14, small 12, page title 28" sentence | 105-119 | New scale (§3). Mention `e2e/type.spec.ts` with new numbers |
| Group labels "14 px / 650 / `--ink-2`, sentence case" | 122 | 13 px / 600 / `--ink-2`, sentence case. Eyebrow caps only above a hero title |
| Space table: `--r-1`/`--r-2` "12 · 20", `--blur` "18px 1.4", `--top` "56 px top bar", `--dock` 56, `--press` 120 | 127-143 | 14 · 28 · `--r-card` 24; blur 24 px / 1.8; `--top` = room the floating capsule needs; `--dock` 64; press 100; add spring row |
| Navigation bullet "On a laptop a glass top bar…" | 200-205 | Floating glass capsule, 52 px, 16 px from top, centred, hides on scroll down. Search is a round glass button, the avatar its own glass circle |
| Glass bullet "only for bars that float over photos" | 241-245 | Add sheets ("glass background over scrim") and the capsule; keep the reduced-transparency rule verbatim |
| Dialogs: "`--raised` with an `--r-2` radius" | 187 | Sheets: glass over `--scrim`, `--r-2` top corners (28), rise on a spring |
| §3 table, Navigation row "glass top bar" | 366 | Floating capsule |
| §5 checklist "Could any border, box or shadow be removed" | 386 | Keep. Add "Does chrome recede on scroll?" and "Spring settles, no fixed-duration gesture end?" |

**Keep as written:** §1.2 never crop without consent; §1.4 one accent for selection and focus;
§1.5-1.8 charts and small multiples; §1.10 same thing, same place; "photos are never rounded"
(grids); per-account look §2 ¶2 (dials only move tokens); glass `prefers-reduced-transparency`
asked straight; no 1 px lines; `--fine` seams; 44 px `--target`; `--field-phone`; safe areas;
the z-index layer table; Home bullet (another agent's, leave it alone).

### `docs/TECH_DECISIONS.md`

Record it in **"## Typefaces (decided 2026-10-14)"** (lines 205-216). Retitle it "decided
2026-10-15", put Inter first, and move Atkinson to "Larger text face". The "Frontend" bullet
"No runtime dependencies at all" stays true: fonts are vendored files, not packages.

Verified online today from the unpkg listing and `metadata.json` of `@fontsource-variable/inter`:

- Fontsource **5.3.0** (latest dist-tag), upstream Inter **v20** from google/fonts, modified
  2025-09-10. Licence **OFL-1.1**, "Copyright 2016 The Inter Project Authors
  (https://github.com/rsms/inter)". Ship `LICENSE` as `static/fonts/Inter-OFL.txt`.
- Axes: `wght` 100-900, **`opsz` 14-32** (default 14), `ital` 0-1.
- Files to vendor (Atkinson's pattern, latin + latin-ext, upright only):
  `inter-latin-opsz-normal.woff2` (72,920 B) and `inter-latin-ext-opsz-normal.woff2`
  (133,336 B). The `wght`-only files are smaller (48,256 / 85,068 B) but have no opsz.
  Italic isn't needed: `--voice-style: italic` is Album-only, in Newsreader.
- Fontsource names the family `'Inter Variable'`. We write our own `@font-face`, so call it
  `'Inter'`, take Fontsource's `unicode-range` lines, and use `format('woff2')`.
- The "Inter Display cut for ≥ 28 px" in the design system doesn't need a second family. The
  opsz axis is the Display design: with `font-optical-sizing: auto` (now only on h1/h2 in
  `base.css`, so move it to `body`), text at 32 px and up gets the Display shapes, and 14-32
  blends between them.
- **Not verified:** whether the Google Fonts build keeps `tnum` (tabular figures; `base.css`
  turns them on everywhere) and `cv`/`ss` features. Slice 1 checks this with a browser unit
  test: in `.data`, `"1111"` and `"0000"` render at the same width in Inter. Safari's opsz
  mapping (px vs pt) is also unchecked; look at a 56 px title on an iPhone.

## 3. Token diff (Safelight; Album notes after)

**Colour, dark** (`themes.css :root`)

| Token | Now | Flight |
| --- | --- | --- |
| `--bg` | `#0d0f12` | `#000000` |
| `--raised` | `#171a1f` | `#111214` |
| `--fill` | `#23272d` | `#1c1d20` |
| `--ink` / `--ink-2` / `--ink-3` | `#f1f2f4` / `#a3a9b3` / `#6b717c` | `#f5f5f7` / `#a1a1a6` / `#6e6e73` (8.2:1 and 6.6:1 on bg/fill) |
| `--hairline` | `#262a31` | `#1c1d20` (tile placeholder; keep the token) |
| `--scrim` | `rgb(4 5 7 / .66)` | `rgb(0 0 0 / .6)` |
| `--lift` | `0 10px 30px rgb(0 0 0/.38)` | `0 20px 60px rgb(0 0 0/.5)` |
| `--glass-edge` *(new)* | — | `inset 0 0 0 0.5px rgb(255 255 255 / .12)` |
| `--scrim-photo` *(new, first block beside `--on-photo`, theme-independent)* | — | `linear-gradient(to top, rgb(0 0 0/.72), transparent 55%)` |
| accent `--acc-l/-c/-h`, `--on-accent`, `--ok`, `--fail` | 0.82/0.14/72 … | unchanged (amber already matches) |
| `--check` svg stroke | `%230d0f12` | `%23000000` |

**Colour, light** (both light selectors): `--bg #f5f5f7`, `--raised #ffffff`, `--ink #1d1d1f`
(15.5:1), **`--ink-2 #636366`** (Flight says `#6E6E73`, which fails 4.5:1 on a fill), `--fill
#e8e8ed`, `--ink-3 #8e8e93`, `--glass-edge inset 0 0 0 0.5px rgb(0 0 0 / .06)`. Accent L 0.5
stays.

**Derived** (`tokens.css`, keep them derived so Album and light follow):
`--glass: color-mix(in oklab, var(--raised) 62%, transparent)` (was 74 %; matches
`rgb(22 22 24/.62)` closely and passes "no colour of its own"). `--blur: blur(24px)
saturate(1.8)` (was 18 px / 1.4).

**Type**: keep the old names as aliases in slice 1 so screen slices migrate on their own.
Delete the aliases in the last slice.

| Old (uses) | New token | Value | Alias in slice 1 |
| --- | --- | --- | --- |
| `--fs-12` (24) | `--fs-13` | 0.8125rem / 500 | `--fs-12: var(--fs-13)` |
| `--fs-14` (24) | `--fs-15` | 0.9375rem / 500 | `--fs-14: var(--fs-15)` |
| `--fs-16` (15) | `--fs-17` | 1.0625rem / 500 | `--fs-16: var(--fs-17)`, root moves to `--root: 1rem` |
| `--fs-20` (9) | `--fs-22` | 1.375rem / 650 / `--track-22` −0.015em | yes |
| `--fs-28` (5) | `--fs-34` | 2.125rem / 700 / `--track-34` −0.022em | yes |
| `--fs-40` (5) | `--fs-display` | 3.5rem, phone 2.5rem / 700 / `--track-display` −0.03em | yes |
| — | `--fs-11` + `.eyebrow` | 0.6875rem / 600 / `--track-eyebrow` +0.08em, uppercase | — |
| `--font-ui` | `'Inter', ui-sans-serif, system-ui, …` | `--font-large: 'Atkinson Hyperlegible Next', …` | — |
| `--title-weight` 750 | 700 | | |

All sizes stay in rem, so the text dial multiplies them. Line heights: add `--lh-display: 1.05`.

**Shape**: `--r-1` 12→**14px**, `--r-2` 20→**28px**, new `--r-card: max(0px, calc(var(--r-2) - 4px))`
(24, and it follows the corners dial), `--r-pill`, `--check-radius` unchanged. Grid photos 0.

**Space/layout**: `--s-9: 6rem` (96, Flight's scale has it). `--page-x` 24→**32px** laptop,
12→**16px** phone. `--dock` 56→**64px**. `--top` → room the capsule takes: `calc(var(--s-4) +
52px + var(--s-2))`. New `--capsule: 52px`.

**Motion**: `--press` 120→100ms; `--motion`, `--motion-sheet`, `--ease`, `--ease-sheet`
unchanged (already Flight's). New `--ease-spring: linear(…)` is generated from `lib/spring.ts`
with k 300 / c 30 (see §4). A unit test fails if the CSS string drifts from the helper's
output.

**How the Album theme and the dials survive**

- **Album** (`data-look='album'`): keeps graphite `#181817`, Newsreader titles, `--r-1 3px /
  --r-2 8px / --gutter 3px` (tokens.spec unchanged), and gets `--track-22/-34/-display: 0`
  (negative tracking hurts a serif). `--glass`/`--blur` follow it automatically because
  they're derived.
- **`--acc-h`**: no change. Lightness and chroma stay per theme, so the 24-hue sweep still holds.
- **`--r-1/--r-2`** (corners dial 0-22): `apply.ts` `THEMES_OWN.safelight.corners` 12→14,
  `SURFACE_PER_CONTROL` 5/3→2, and the same in `app.html`'s first-paint script. `--r-card`
  follows `--r-2`. Grid photos ignore the dial.
- **`--gutter`** (0-8): no CSS change. Separately, `apply.ts` `PHOTO_GAP = 3` is what the grid
  uses when the dial is left alone (`state/settings.svelte.ts:24`), but CSS `--gutter` is 2px.
  Flight says 2 px gutters, so set `PHOTO_GAP = 2` (apply.spec) or decide the default is 3 on
  purpose.
- **`--text-scale`** (0.9-1.25): no change; every new size is rem. The Display title at 125 %
  is 70 px. Check that the phone hero still fits.
- **Larger text face**: there's no look field for it. `Look` (`look/sheet.ts`) and
  `domain/look.py` have theme, mode, dials and switches but no face. Adding a `face` switch is
  a change to the look sheet, the API contract and the backend validation, which is a **hard
  stop for the owner**, so it gets its own issue. Until then Atkinson stays a declared token
  (`--font-large`) and isn't reachable, so it costs no download.

## 4. Motion infrastructure

| Exists | What it does | Flight gap |
| --- | --- | --- |
| `lib/motion.ts` | `withTransition` (View Transition or a plain change, reduced-motion aware); `movePage` sets `data-page-move` forward/back/switch with `--page-shift` | none. Push/pop slide and places cross-fade are already Flight's. Keep |
| `utilities.css` 66-180 | VT timing = `--motion-sheet`/`--ease`; `page` name only during moves; bars `bar`/`dock`/`dock-search` held still; keyframes; reduced-motion off | the laptop capsule needs `view-transition-name: bar` kept (it is). The shared-element zoom photo↔tile already exists (loupe) |
| `lib/sheet-drag.ts` | pointer drag down; `shouldClose(pulled, ms)` = ≥96 px or ≥0.6 px/ms over ≥24 px; release = CSS transition back | average speed, not release speed; no spring settle; phone only |
| `gesture.ts`, `PhotoStage` | see FINDINGS swipe jank: 50 px distance only, fixed 200 ms settle | owned by the viewer slice |
| Nav lens | CSS `transform` on `--motion-sheet`/`--ease-sheet` | fine; could use `--ease-spring` |
| `svelte/motion` `Spring` (Svelte 5.57, already installed) | reactive `$state` spring | **not suitable**: stiffness/damping are 0-1 numbers, not physical k/c; it can't be seeded with a release velocity; and it's reactive state, while FINDINGS asks for rAF `translate3d` with no Svelte state per frame |

**Proposed `web/src/lib/spring.ts`** (no new dependency; TECH_DECISIONS says the web app has no
runtime deps, and this doesn't add one), about 60 lines, pure and unit-tested first:

- `step(state {x, v}, target, {stiffness, damping, mass}, dt) → {x, v}`: semi-implicit Euler
  in fixed 1/240 s sub-steps, so it behaves the same at 60 and 120 Hz.
- `settled(state, target, precision = 0.1 px, 0.05 px/ms)`.
- `animate({from, to, velocity, config, onFrame, onRest}) → {stop(), retarget(to)}`: one rAF
  loop, writes through `onFrame(x)` (the caller sets `style.translate`), and lands at `to` at
  once under `prefers-reduced-motion`.
- `velocityTracker()`: the last ~80 ms of pointer samples → px/ms at release. sheet-drag and
  the loupe both need this.
- `SPRINGS = { snappy: {stiffness: 400, damping: 30}, gentle: {stiffness: 300, damping: 30} }`,
  mass 1 (ζ ≈ 0.75 and 0.87, slightly underdamped like iOS).
- `toLinearEasing(config, samples = 40) → 'linear(…)'`, for CSS-only springs (press, lens,
  sheet rise). `linear()` is in Chrome 113+, Safari 17.2+, Firefox 112+. Under that, fall back
  to `--ease-sheet`.
- Tests: boundaries (zero distance, settles within N frames, overshoot < 5 % for `gentle`,
  velocity seeding moves further, retarget mid-flight is continuous, reduced motion = one
  frame, `dt` independence).

First users, each in its own slice: `sheet-drag.ts` (release → `animate` with tracked
velocity; `shouldClose` takes release velocity instead of average), the loupe pager, and zoom
spring-back.

## 5. Shell

PR #82 changed `routes/+layout.svelte` on `origin/main`: it imports and mounts `InstallTip`
after `<main>`. This worktree is behind, so **rebase the shell slice on `origin/main` first**.
`InstallTip` positions itself over the dock with `--bar`, so changing `--dock`/`--bar` moves it
too; re-run `e2e/install-tip.spec.ts`.

| File | Today | Flight change |
| --- | --- | --- |
| `Nav.svelte` (laptop ≥1024) | `position: sticky; top: 0; height: var(--top)`, full-width glass strip; places as pills with `--lens` background; `.search` a wide `--fill` pill linking to /search; avatar in `.me` | `position: fixed`, centred (`inset-inline: 0; margin-inline: auto; width: fit-content`), `top: calc(env(safe-area-inset-top) + var(--s-4))`, height `--capsule`, `--r-pill`, glass + `--glass-edge` + `--lift`. Reuse the phone's sliding `::before` lens for laptop too (one code path, transform only). Search: a round glass button beside the capsule, a link for now; "expands into a field" is a later step. Avatar: its own glass circle at far right. **Hide on scroll:** `translate: 0 calc(-100% - var(--s-4) - env(safe-area-inset-top))` when root has `data-chrome='away'`, transition on `--ease-spring`. Phone dock: same attribute may shrink it later; for now only `--dock` 64 |
| new `lib/scroll-chrome.svelte.ts` | — | one passive `scroll` listener + rAF, sets `data-chrome='away'\|null` on root. Hide after ≥ 12 px down, show on any ≥ 6 px up, always shown within 24 px of top, while focus is inside `nav`, while a menu or dialog is open, and on keyboard focus. TDD: pure `decide(prevY, y, state, context) → state` unit, edge cases (bounce/overscroll negative y, page shorter than the screen, resize, route change resets to shown) |
| `+layout.svelte` | `.app` grid `auto 1fr` (bar row + main); phone `main` pads for safe areas + `--bar`; theme-color `#0d0f12`; toast offsets | grid becomes one row (nav is fixed on both sizes). Laptop `main` gets `padding-top: var(--top)` so the first content clears the capsule. Theme-color `#000000`. Toast offsets unchanged |
| `--top` users (7: `Nav`, `Timeline`, `base.css`, `routes/+page.svelte` Library, `albums/[id]/print`, `tokens.css`, `SelectionBar` via `--bar`) | sticky offsets by a 56 px solid bar | Sticky things (month headings, Library head) **stick at the safe-area top**, not under the capsule. While the capsule shows they shift down with `translate` (`--chrome-shift`, transform only, never `top`, which would be layout). `Timeline.svelte` and `routes/+page.svelte` belong to the Library slice. The shell slice only sets the tokens and the attribute |
| `PageHead.svelte` | flex row: back, titles (h1 `--fs-28`), actions + avatar (phone); phone-only `.compact.glass` title fades in when the h1 leaves the top (IntersectionObserver) | Large title `--fs-34`, `--track-34`, optional `eyebrow` prop. Collapse: keep the observer but drive a continuous `--collapse` 0→1 from a second observer threshold list (`threshold: [0, .25, .5, .75, 1]`), scaling the h1 (`transform-origin: left; scale`) and fading in the compact title. Transform/opacity only. On a laptop the compact title shows in the capsule's place when the capsule is away (same `data-chrome`). Avatar on a phone stays in the row (Flight: "avatar → settings") |

Out of scope here: `routes/home/**` and `components/home/**` (another agent's per-person
sections). The Home route doesn't use `PageHead`.

## 6. Build order (PR-sized slices)

Each slice is TDD: change the guard first (red), then the code. Run `just check` plus the named
e2e on desktop and phone. Slices 2-8 depend only on 1 (and 3 on 2); after slice 2 they don't
touch each other's files.

| # | Slice | Owns (files) | Guards / tests it changes | Risk |
| --- | --- | --- | --- | --- |
| 0 | **Docs first**: DESIGN_PRINCIPLES rewrite (§2 table), TECH_DECISIONS Typefaces | `docs/DESIGN_PRINCIPLES.md` (not the Home bullet), `docs/TECH_DECISIONS.md` | none | low. Must merge before 1 so the guards change "on purpose". Owner signs off on tracking/caps and the light `--ink-2` deviation |
| 1 | **Foundation**: Inter files + licence, `fonts.css`, `themes.css` values, `tokens.css` (new tokens + aliases), `base.css` (opsz on body, `--root`), `utilities.css` (`.glass` edge, `.eyebrow`), `apply.ts` + `app.html` corners ratio, `PHOTO_GAP`, `manifest.webmanifest`, `favicon.svg` | those files + `static/fonts/` | style-guard (tracking allowlist, licences), tokens.spec, themes.spec (+ new colours, scrim-photo contrast), apply/boot.spec, new tnum and photos-unrounded tests; e2e type/look/exposure/ruler/loupe font + colour assertions | **medium.** Every screen shifts at once: sizes +1-6 px wrap text and break e2e text-fit and screenshot specs (`fit.spec.ts` measures text width with the real font). Aliases keep it to value changes only. The theme-color meta is in `+layout.svelte`: one line, flag it in the PR |
| 2 | **Spring helper** | new `lib/spring.ts` + spec; `sheet-drag.ts` (+spec) as first user; `--ease-spring` value in `tokens.css` | sheet-drag.spec, new spring.spec | low. Pure code, one consumer |
| 3 | **Shell**: floating capsule, hide-on-scroll, large-title collapse | `Nav.svelte`, `+layout.svelte`, `PageHead.svelte`, `Avatar.svelte`, new `lib/scroll-chrome.svelte.ts`, `nav.ts` if needed | `shell.spec.ts`, `routes.spec.ts`, `edges.spec.ts`, `install-tip.spec.ts`, `back.spec.ts`; new scroll-chrome unit spec | **high.** Every page. Sticky offsets, toast/InstallTip/selection pill stacking, keyboard focus into a hidden bar, VT `bar` naming. Rebase on main (#82) |
| 4 | **Library**: chips, time ruler, grid press/hover, sticky headings on the safe top | `routes/+page.svelte`, `LibraryHead`, `FilterChips`, `ui/Chip`, `TimeRuler`, `Timeline`, `PhotoGrid`, `JustifiedGrid`, `SelectionBar`/`SelectionActions` | ruler, grid, filters, selection-share, actions specs | medium |
| 5 | **Viewer**: 3-slot pager on `spring.ts`, glass chrome, Details sheet | `Loupe`, `PhotoStage`, `PhotoBar`, `PhotoInfo`, `gesture.ts`, `zoom.ts`, `loupe.svelte.ts`, `info-sheet.svelte.ts` | loupe, loupe-gestures, back-info, perf specs | **high.** Gesture rewrite (FINDINGS 1-7). Own PR, no other visual changes |
| 6 | **Sheets and controls**: `Dialog` as glass sheet (28 radius, spring rise), `Menu`, `buttons.css`, `fields.css`, `ui/*` | `Dialog`, `Menu`, `ui/Segmented`, `ui/TileGroup`, `ui/TileRow`, `ui/IconButton`, `buttons.css`, `fields.css` | dialogs/menu/ui unit specs, date-field, axe in every e2e | medium. Shared by every screen: merge before 7-8 |
| 7 | **Collections family**: Collections, People, Person, Albums, Album, Search | `routes/collections`, `people`, `albums` (not `print`), `search`, `CollectionRows`, `PersonHero`, `AlbumHero`, `Portrait`, `SearchSuggestions` | collections, people, albums, discover specs | medium |
| 8 | **You / Admin / Sign-in / Review / Trash** | `routes/settings`, `admin`, `login`, `setup`, `review`, `trash`, `components/admin/**`, `PinPad`, `Devices` | settings, admin-*, auth, review specs | low-medium |
| 9 | **Cleanup**: delete `--fs-12…40` aliases; move `--track-*` guard to the final allowlist | `tokens.css`, any straggler | style-guard: no `--fs-(12\|14\|16\|20\|28\|40)` anywhere | low. Only after 4-8 (and Home) merged |
| — | **Larger text face** (needs owner OK: look sheet + API + backend validation) | `look/sheet.ts`, `domain/look.py`, `api/schemas.py`, `LookForm`, contract doc | look api/unit tests, look.spec | medium. Hard stop until an issue exists |

Collision rules: only slice 1 edits `themes.css`/`fonts.css`, and only slices 1, 2 and 9 edit
`tokens.css` (2 adds one line). Screen slices use the new token names but don't add tokens; if
one needs a token, it goes through a small follow-up to slice 1. Home (other agent) picks up
`--r-card`, `--scrim-photo`, `.eyebrow`, `--fs-display` after slice 1 merges.
