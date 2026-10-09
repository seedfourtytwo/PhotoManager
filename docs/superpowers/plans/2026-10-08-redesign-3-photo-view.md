# Redesign 3 of 4: Photo view, selection pill, time ruler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the photo view a floating glass bar (a two-line readout and five actions) and gestures that follow the finger, replace the date scrubber with a ticked time ruler on both devices, and turn the selection bar into a floating pill.

**Architecture:** What a touch means is decided by one pure recogniser (`gesture.ts`); where a month sits on the ruler by another pure module (`ruler.ts`); what the readout says by a third (`readout.ts`). All three are unit-tested in node. `Loupe.svelte`, `SelectionBar.svelte` and the new `TimeRuler.svelte` are the thin shells on top. Opening and closing the photo view goes through `withTransition` (`motion.ts`), which uses the browser's View Transitions where they exist and does the change plainly elsewhere.

**Tech Stack:** SvelteKit 2 (static), Svelte 5 runes, TypeScript strict, Vitest 4 (node project for `*.spec.ts`, browser project for `*.svelte.spec.ts` with `vitest-browser-svelte`), Playwright e2e (mock API and real backend), pnpm.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` §4.3, §4.4, §4.5, §6 (gestures), §7 step 3, §8. Issue: seedfourtytwo/PhotoManager#11. Terms: `CONTEXT.md`.

## Global Constraints

- Web only. No backend, schema or API change and no new npm dependency; where the spec needs one, stop and report (see "Not built" below).
- Only tokens in components: no raw colours, sizes or spacings outside `tokens.css`, `themes.css`, `fonts.css`.
- The accent marks selection and focus, and "now" on the ruler (spec §3). A pressed Favourite is full ink, not the accent.
- Every icon in a bar carries its word. Every gesture has a visible button that reaches the same state.
- Accessible names that tests and screen readers already rely on stay exactly: `Photo viewer`, `Photo actions`, `About this photo`, `Close`, `Info`, `Favourite`, `Private`, `Download`, `Edit`, `Fix date`, `More like this`, `Restore`, `Previous photo`, `Next photo`, `Selected photos`, `Clear selection`, `Jump to date`, and every selection action label (`Move to trash` keeps its words; the spec's "Delete" names the action, and the Trash page already uses "Delete for good" for the other thing).
- Keyboard shortcuts of the photo view do not change: ← → F I Esc.
- Phone: 44 px touch targets (`--target`), safe-area insets respected, nothing wraps to a second line.
- E2E tests may be edited only where this plan names them, each with the spec line that asks for it; no assertion is weakened.
- Real photos never enter the repo, screenshots or fixtures. Port 8420 and `~/PhotoAssistant` are not touched.
- Branch `feat/11-photo-view` from `origin/main`. Conventional Commits; each message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never bare `git stash`.

## Not built in this step (needs the owner)

| Spec says | Why not | What ships instead |
|---|---|---|
| Readout line two: aperture · shutter · ISO · focal length | The API (`AssetDetail`) and the database carry none of them: a schema and API change | camera model · pixel size · file name |
| **Share** in the photo bar and in the pill | Nothing defines what Share does for a photo; the one web-only reading (the phone's share sheet) hands photo data to other apps, which is an `AGENTS.md` hard stop | Download keeps its place; the bar is Favourite · Download · Album · Edit · More |
| Sideways swipe by native snap-scrolling (§6) | The swipe stays in the recogniser, where the photo follows the finger through a transform; a three-pane scroller could not be checked on iOS Safari from here | the same gesture, the same thresholds |
| Dragging the ruler scrolls while the finger moves | A far month may need many pages; the jump stays at release, the needle follows the finger meanwhile | as the scrubber did |
| Long-press then drag, dragging back to take photos out again | The drag reuses the range selection every page already has (`ontoggle(id, true)`), which only adds | a run that grows with the finger |

## File Structure

| File | Responsibility |
|---|---|
| `web/src/lib/icons.ts` | Ten more icons for the two bars. |
| `web/src/lib/gesture.ts` (new) | Pure: what a press and its release mean; where a drag pulls the photo. |
| `web/src/lib/readout.ts` (new) | Pure: the two lines of the photo bar. |
| `web/src/lib/motion.ts` (new) | `withTransition`: a View Transition where the browser has them. |
| `web/src/lib/loupe.svelte.ts` | `openPhoto` / `closePhoto` run inside a transition from and to the tile. |
| `web/src/lib/ruler.ts` (new) | Pure: months on a time-linear ruler, year marks, the month at a point. |
| `web/src/lib/components/TimeRuler.svelte` (new) | The ruler: vertical on a laptop, horizontal and fading on a phone. Replaces `DateScrubber.svelte` (deleted). |
| `web/src/lib/components/Loupe.svelte` | Glass bar (readout, five actions, More), gestures through the recogniser. |
| `web/src/lib/components/Menu.svelte` | Optional icon on the button, pressed rows, bindable `open`. |
| `web/src/lib/components/SelectionBar.svelte`, `SelectionActions.svelte` | The floating pill; Esc clears. |
| `web/src/lib/components/PhotoGrid.svelte` | Long-press then drag selects a run of photos. |
| `web/src/lib/tokens.css` | `.action` (an icon over its word), `--pill`, view-transition timing. |
| `web/src/routes/+page.svelte`, `people/[id]/+page.svelte`, `trash/+page.svelte`, `+layout.svelte` | Ruler on both devices; Esc handled by the pill; the toast clears the pill. |
| `web/e2e/photo-view.spec.ts` (new), `web/e2e/helpers.ts` | Journeys for the three pieces; `loupeAction`, `touchDown` (a finger that rests, moves and stays down), `transitionOver`. |

---

### Task 1: Icons for the two bars

**Files:** Modify `web/src/lib/icons.ts`, `web/src/lib/icons.spec.ts`.

**Interfaces:** Produces `IconName` extended with `'album' | 'close' | 'date' | 'download' | 'edit' | 'favourite' | 'info' | 'more' | 'restore' | 'trash'`.

- [ ] **Step 1: Failing test** — in `icons.spec.ts` the first test becomes `has the icons the shell and the action bars need` and expects the thirteen names, sorted. Run `cd web && pnpm test src/lib/icons.spec.ts`: FAIL (three names).
- [ ] **Step 2: Implement** — add the paths (drawn on the 24 grid, every path starting with an absolute `M`; circles written as two arcs).
- [ ] **Step 3: Run, commit** — `feat(ui): icons for the photo bar and the selection pill`.

### Task 2: The gesture recogniser

**Files:** Create `web/src/lib/gesture.ts`, `web/src/lib/gesture.spec.ts`.

**Interfaces:**

```ts
export type Point = { x: number; y: number; t: number };
export type Gesture = 'tap' | 'double-tap' | 'previous' | 'next' | 'details' | 'close';
export const DOUBLE_TAP_MS = 300;
/** What a press that ended means; null for a press that means nothing. Swipes are touch only. */
export function recognise(down: Point, up: Point, lastTap: Point | null, touch: boolean): Gesture | null;
/** How far the photo is pulled while the finger is down: one axis, chosen once the finger has left the tap slop. */
export function pull(down: Point, now: Point): { x: number; y: number };
```

Test names (`gesture.spec.ts`):

- `a short press that stays put is a tap`
- `a press held longer than half a second is nothing`
- `a second tap within 300 ms and 30 px is a double tap; later or further away it is a tap again`
- `more than 50 px sideways is next (leftwards) or previous (rightwards)`
- `more than 60 px up is details; more than 80 px down is close`
- `a drag released short of its threshold is cancelled: no gesture` (each direction, one pixel short)
- `a diagonal drag goes to its longer axis`
- `a mouse can tap and double tap but not swipe`
- `pull: nothing inside the slop, then only the longer axis, and never upwards`

- [ ] **Step 1:** write the tests; run: FAIL (cannot resolve `./gesture`).
- [ ] **Step 2:** implement with the thresholds the loupe uses today (10 px slop, 500 ms, 50 / 60 / 80 px).
- [ ] **Step 3:** run, commit — `feat(ui): one pure recogniser for the photo view's gestures`.

### Task 3: Photo view — gestures that follow the finger, double-tap

**Files:** Modify `web/src/lib/components/Loupe.svelte`, `web/e2e/helpers.ts`; create `web/e2e/photo-view.spec.ts`.

- [ ] **Step 1: Failing e2e tests** (`photo-view.spec.ts`, phone project):
  - `phone: a double tap on the photo favourites it, like the Favourite button`
  - `phone: the photo follows the finger and springs back from a short drag`
  - `phone: each gesture and its button reach the same state` (swipe left ↔ Next photo, swipe right ↔ Previous photo, swipe up ↔ Info, pull down ↔ Close)
- [ ] **Step 2: Implement** — `onstagedown` / `onstagemove` / `onstageup` call `pull` and `recognise`. A tap waits `DOUBLE_TAP_MS` before it toggles the chrome, so a double tap never flickers it. The stage sets `--pull-x` / `--pull-y`; the photo translates by them and eases back when released. The photo sits in a `.frame` that has the photo's own aspect ratio (container units), so what moves is the photo, not the letterbox.
- [ ] **Step 3: Run** — `pnpm e2e photo-view loupe browse`: green on both projects. Commit — `feat(ui): the photo follows the finger; double-tap favourites`.

### Task 4: Photo view — the glass bar

**Files:** Create `web/src/lib/readout.ts`, `web/src/lib/readout.spec.ts`; modify `Loupe.svelte`, `Menu.svelte`, `Menu.svelte.spec.ts`, `tokens.css`, `web/e2e/helpers.ts`, and the e2e tests named below.

**Interfaces:**

```ts
/** The two lines of the photo bar: when and where, then what took it and what it is called. */
export function readout(asset: AssetOut, detail: AssetDetail | null): [string, string];
```

`Menu` gains `icon?: IconName` (the button shows the icon over its word), `open` becomes bindable, and `MenuItem` gains `pressed?: boolean` (rendered as `aria-pressed`).

Test names:

- `readout.spec.ts`: `line one is date · time · place, the place as its most local name`, `line one leaves the place out when there is none`, `line two is camera · size · file name, the name without its folders`, `line two is the size alone before the details arrive`, `an unknown size is left out`
- `Menu.svelte.spec.ts`: `shows an icon over its word when given one`, `a pressed row says so`
- `photo-view.spec.ts`: `the bar reads the photo's date, time and file name in the data face`, `the bar holds Favourite, Download, Album, Edit and More; More holds the rest`, `Album adds the open photo to an album`, `Escape closes More, not the photo view`

- [ ] **Step 1:** unit tests first (red), then `readout.ts` and the `Menu` props (green).
- [ ] **Step 2:** e2e tests (red), then the bar: `.top` stays the `Photo actions` toolbar and becomes a layer over the stage (Close top left, Info and Full screen top right, the bar bottom centre, glass). The bar: readout in `.data`, then the actions as `.action` buttons. More (a `Menu`) holds Private, Fix date and More like this. The chrome does not go idle while More is open. On a phone the info sheet covers the bar.
- [ ] **Step 3: Existing e2e tests that must change** — the spec (§4.3: "five actions with icon and label: Favourite, Share, Album, Edit, More") moves Private, Fix date and More like this behind More. `helpers.ts` gains `loupeAction(page, name)` (opens More when the button is not on the bar). Changes, one line each:
  - `loupe.spec.ts` `owner/admin can make a photo private from the loupe`: reach Private through More; reopen More before reading `aria-pressed`.
  - `loupe.spec.ts` `more like this, when the models are installed`: reach it through More.
  - `actions.spec.ts` `fix date from the loupe: set an exact date`: reach Fix date through More.
  - `screenshots.spec.ts`: Fix date through More; a new shot `04c-loupe-more`.
- [ ] **Step 4: Run** — unit, `pnpm check`, `pnpm lint`, `pnpm e2e`. Commit — `feat(ui): glass bar in the photo view: readout and five actions`.

### Task 5: Opening and closing from the tile

**Files:** Create `web/src/lib/motion.ts`, `web/src/lib/motion.spec.ts`; modify `web/src/lib/loupe.svelte.ts`, `Loupe.svelte`, `tokens.css`.

**Interfaces:**

```ts
type Env = { start?: (change: () => Promise<void>) => { finished: Promise<void> }; reduced: boolean };
/** Run a change of what is on the page as a View Transition where the browser has them, plainly elsewhere. Resolves when it is over. */
export function withTransition(change: () => void | Promise<void>, env?: Env): Promise<void>;
```

Test names (`motion.spec.ts`): `runs the change inside a view transition where the browser has them`, `runs it plainly, at once, where it has none`, `runs it plainly under reduced motion`, `a transition the browser skips still resolves`.

- [ ] **Step 1:** tests red, `motion.ts` green.
- [ ] **Step 2:** `openPhoto` names the tile `photo` for the old picture and pushes the state inside the transition; `closePhoto` goes back inside one and names the tile for the new picture. The loupe's `.frame` carries `view-transition-name: photo`. Where the browser has no view transitions the loupe fades in (`@supports not`). The existing `loupe.spec.ts` unit tests stay untouched and green (node has no `document`, so the change runs at once).
- [ ] **Step 3:** e2e `opening and closing run a view transition between the tile and the photo` (the frame carries the name, the tile only for the length of the transition). Run the whole e2e suite: the loupe is opened and closed in most journeys.
- [ ] **Step 4: Existing e2e behaviour that must change** — a page takes no input while a view transition runs (§4.3: "Opening and closing uses a View Transition"), so a touch sent a few milliseconds after the click that opened the photo lands on nothing. No test file is edited for it: `touchDown` (which `touchSwipe` now calls) waits for a running transition before the finger comes down. This is what keeps `loupe.spec.ts` `phone: real vertical swipes show info (up) and close (down)` green.
- [ ] **Step 5:** `closePhoto` ignores a second request while one is under way (Escape plus the dialog's own close event), so the page is never left by going back twice. Commit — `feat(ui): the photo view opens from its tile and closes back to it`.

### Task 6: The time ruler

**Files:** Create `web/src/lib/ruler.ts`, `web/src/lib/ruler.spec.ts`, `web/src/lib/components/TimeRuler.svelte`; delete `DateScrubber.svelte`; modify `small.svelte.spec.ts`, `web/src/lib/timeline.ts` (+ spec), `web/src/routes/+page.svelte`.

**Interfaces:**

```ts
export type RulerMonth = { key: string; count: number }; // newest first
/** Where a month sits: 0 at the newest month with photos, 1 at the oldest, linear in time. */
export function position(months: readonly RulerMonth[], key: string): number;
/** The month with photos nearest to a point of the ruler. */
export function monthAt(months: readonly RulerMonth[], at: number): string | null;
/** One mark per calendar year, from its December (`at`) to its January (`end`); `label` on as many as `room` allows, evenly. `key` is where a tap on it goes. */
export function yearMarks(months: readonly RulerMonth[], room: number): { year: string; at: number; end: number; key: string; label: boolean }[];
/** Calendar months from the newest to the oldest, for the small ticks. */
export function span(months: readonly RulerMonth[]): number;
/** "Dec 2019", for the needle's tag. */
export function monthTag(key: string): string;
```

`TimeRuler` props: `months`, `current`, `onjump`, `orientation: 'vertical' | 'horizontal'`, `fades?: boolean`.

Test names:

- `ruler.spec.ts`: `the newest month is at 0, the oldest at 1, and time between them is linear`, `one month alone sits at 0`, `a month outside the range is clamped`, `monthAt finds the nearest month that has photos`, `monthAt clamps points beyond the ends`, `every year gets a mark from its December to its January, cut to the ruler`, `labels thin out evenly when there is no room for all`, `a tap on a year goes to that year's newest month with photos, or the next older one`, `no months, no marks`, `monthTag writes a month short enough for the needle`
- `small.svelte.spec.ts` (the `DateScrubber` blocks become `TimeRuler`; §4.4 "Replaces `DateScrubber`"): `labels years along the track and reports the current month`, `jumps by keyboard` (both unchanged), `the needle shows the month under the pointer while dragging and jumps once, on release`, `a cancelled drag ends the drag: no jump, and the needle goes back`, `tapping a year jumps to it`, `horizontal: time runs left to right, the newest month at the right end`, `a fading ruler is hidden until the page scrolls and hides again when idle`
- `photo-view.spec.ts`: `phone: the time ruler shows while scrolling, fades when idle, and a drag along it jumps`, `laptop: the ruler is a column of years at the right edge with the needle on the month in view`

- [ ] **Step 1:** `ruler.spec.ts` red → `ruler.ts` green.
- [ ] **Step 2:** component tests red → `TimeRuler.svelte` green; delete `DateScrubber.svelte`.
- [ ] **Step 3:** the Library page shows it on both devices (hidden on a phone while photos are selected: the pill takes its place). e2e red → green. `grid.spec.ts` and `browse.spec.ts` scrubber tests pass unedited.
- [ ] **Step 4:** commit — `feat(ui): time ruler replaces the date scrubber, on the phone too`.

### Task 7: The selection pill

**Files:** Modify `SelectionBar.svelte`, `SelectionActions.svelte`, `PhotoGrid.svelte`, `PhotoGrid.svelte.spec.ts`, `small.svelte.spec.ts`, `tokens.css`, `+layout.svelte`, `+page.svelte`, `people/[id]/+page.svelte`, `trash/+page.svelte`, `web/e2e/helpers.ts`, and the tests named below.

**Interfaces:** `Action = { label: string; run: () => void; hidden?: boolean; icon?: IconName; more?: boolean }`. An action flagged `more` sits behind More on every device; on a phone the bar also keeps only the first three.

Test names:

- `small.svelte.spec.ts`: `actions flagged for More sit behind it on a laptop too`, `shows an icon beside the word of an action that has one`, `Escape clears the selection`, `Escape in a field or a dialog does not clear it`
- `PhotoGrid.svelte.spec.ts`: `long-press then drag selects up to the photo under the finger`, `a drag before the long press has fired selects nothing`
- `photo-view.spec.ts`: `the selection bar is a floating pill at the bottom centre`, `the pill offers Add to album, Download, Fix date, Move to trash and More`, `phone: long-press then drag selects a run of photos`

- [ ] **Step 1:** unit tests red → `SelectionBar` (pill, icons, `more`, Esc) and `SelectionActions` (order: Add to album, Download, Fix date, Move to trash; Favourite, Hide, Private and the page's extras behind More) green. The pages' own Esc handlers go.
- [ ] **Step 2:** `PhotoGrid`: once the long press has fired, a move onto another tile calls `ontoggle(id, true)` (the run from the pressed photo), and the grid's non-passive `touchmove` listener keeps the page from scrolling under the finger.
- [ ] **Step 3: Existing tests that must change** (§4.5: "count, Add to album, Share, Download, Fix date, Delete, and More" — Favourite and Hide are no longer on the bar):
  - `small.svelte.spec.ts` `a refused Favourite puts every photo back…`: open More before pressing Favourite.
  - `fixes.spec.ts` `the two Hide buttons have different names`: open More before counting.
- [ ] **Step 4:** the toast sits above the pill. Run everything. Commit — `feat(ui): the selection bar is a floating pill; long-press then drag`.

### Task 8: Documents, speed, proof

- [ ] **Step 1:** `docs/DESIGN_PRINCIPLES.md` (the loupe, selection and layout-by-device rows; the time ruler), `docs/wiring/web.md`, `docs/FEATURES.md` wording, the spec's §4.3–4.5 where what shipped differs (the table above).
- [ ] **Step 2:** scroll speed with the ruler and the non-passive listener on: the probe at the top of `web/e2e/perf.spec.ts`, phone project, this branch against `origin/main`.
- [ ] **Step 3:** `just check`, `just e2e-mock`, `just e2e`: all green; record the counts. Run the web tests with `PA_API` pointing at a closed port (`PA_API=http://127.0.0.1:9 just check`): one component test (`admin/pickers.svelte.spec.ts`) lets a request through the dev proxy, which by default reaches whatever listens on 8420, and a real server there answers 401 and fails the run with an unhandled rejection.
- [ ] **Step 4:** `cd web && pnpm screenshots && THEME=light pnpm screenshots`; look at the loupe, selection and library shots on both devices and in both modes.
- [ ] **Step 5:** commit — `docs: photo view, pill and ruler in the design principles; fresh screenshots`. Push, open the PR with the template; do not merge.
