# Home: review + Flight spec

Scope: `/home` (page header, On this day, Rediscover, Memories, Years, Pinned, People, New this
week), the story player, You → "Home shows, in this order", the Add-to-Home-Screen tip, and the
iOS status bar when Home runs as an app.
Sources: screenshots of the synthetic mock library at 1440x900 and 390x844 (Home top, scrolled,
full page; story player; You → Home sections; the tip on an iPhone). They stay on the laptop. Code
read at `origin/main` d20c874 (after #81, #82, #83, #87).
Target: `design-system.md` ("Flight"). Paths are relative to `web/src/` unless they start with `backend/`.

Math used below. This is the same as the other area specs. Laptop content width at 1440 = 1440 − 2×32 = **1376 px**. Phone = 390 − 2×16 = **358 px**.
A rail shows `n.3` cards, so the next card always peeks. Rails bleed to the screen edge and snap
to the 32 / 16 px page inset.

The mock has no On this day today, so it is reviewed from the code. Rediscover is the first
block in the screenshots.

---

## 0. Problems on every block

| # | Problem | Where |
|---|---|---|
| 1 | Page is `#0d0f12`, and `theme-color` is the same grey-blue. Photos never float. | `lib/themes.css:13`, `routes/+layout.svelte:141` |
| 2 | Each block opens with its own h2 line (`--target` tall) plus `--s-6` above it. Seven blocks add about 7 × 92 px of headings and gaps. The type is the default h2 size, not a 22/650 section title. | `HomeSection.svelte:36,38-45` |
| 3 | **Ragged last rows.** Rediscover's dozen, Pinned and New this week are all `JustifiedGrid`, so each one ends in an orphan (Rediscover row 4 on phone is one tile on the left, and laptop row 3 is one tile). | `routes/home/+page.svelte:235-239,256,274` |
| 4 | Rails stop at the page padding instead of the screen edge. The last visible card is sliced flat at the gutter ("Montara, July 201") and does not peek past the edge. | `MemoryRow.svelte:33-42,121-126` with `routes/home/+page.svelte:317-319,396-398` |
| 5 | Every caption sits under its photo (title, then a line), so each card is about 30 % taller than its photo. | `MemoryRow.svelte:24-26,87-94` |
| 6 | A round play mark is drawn on **every** card (8 years mean 8 play buttons). It is noise: the whole card already plays. | `MemoryRow.svelte:22,95-106`, `Hero.svelte:76-87` |
| 7 | Loading is two flat `--hairline` blocks, and the cover block copies the 58 % width bug. No shimmer. | `routes/home/+page.svelte:199-203,364-393` |
| 8 | Nothing moves. There is no Ken Burns drift, the press is an opacity of 0.85, nothing enters, and no shared element links a cover to its story. | `Hero.svelte:56-58`, `MemoryRow.svelte:76-80` |
| 9 | Slashed zeros (Atkinson) in every date and count ("2021", "30 photos"). | font, slice 1 |

---

## 1. Page header and date line

### What is wrong, ranked
1. **A tiny date line sits alone above a big gap.** "Thursday 15 October" (about 15 px, 600, `--ink-2`) sits in a 3.5 rem row. Then `--s-6` and a 44 px "Rediscover" line follow. The first photo starts at y=212 on laptop and y=156 (CSS px) on phone, under about 120 px of near-nothing. `routes/home/+page.svelte:186-190,320-332`, `HomeSection.svelte:36`
2. The h1 "Home" is visually hidden, so the date is the only page title. It is too small to read as one, and too big to read as a footnote. `routes/home/+page.svelte:187-188`
3. On the phone the avatar is a 48 px solid disc beside the date. On the laptop the avatar is hidden here because the top bar has it, which leaves the date alone at the left. `routes/home/+page.svelte:189,383-386`

### Flight spec
| | Laptop | Phone |
|---|---|---|
| With a hero first (the usual case) | No header row. The **lead hero runs under the floating glass top bar**. The date sits **on the photo** in the top-left, 32 px inset, under the bar: 15/600 `--ink` (white on photo) over a top scrim `linear-gradient(to bottom, rgb(0 0 0 / .45), transparent 30%)`. | The hero runs **under the status bar**. The date sits top-left at `safe-area-top + 12`. The avatar is a 36 px glass circle top-right on the photo. |
| First block not a hero (the account put Years first) | iOS large title: the date as a 13/600 `--ink-2` line, then **"Home" 34/700**, 32 px inset. It collapses into the glass bar on scroll (the shell's `PageHead`, slice 3). | Same, at 16 px inset. The avatar sits on the title line. |
| New day while open | The existing `cameBack` keeps working (`:98-101`). The date cross-fades over 200 ms. | Same. |

---

## 2. Lead hero: Rediscover (and On this day)

### What is wrong, ranked
1. **About 58 % wide on laptop, with the title floating at the bottom of a black void.** The frame is `width: min(58%, 70vh × ratio)` in a flex row. The words are `flex: 1; align-items: flex-end`, so "Five years ago" lands bottom-right of an empty 560×450 area. `Hero.svelte:89-106` (width at `:97`)
2. **Two titles for one photo.** The h2 "Rediscover" sits above the photo, and the 40 px "Five years ago" sits beside or under it. The hierarchy is upside-down: the section name gets its own line, and the memory is a caption. `routes/home/+page.svelte:226-232`, `Hero.svelte:64-70`
3. **The photo is letterboxed, never cropped** (`object-fit: contain`, `max 75svh × ratio`). A portrait cover becomes a narrow column centred in black. `Hero.svelte:43-58`
4. On the phone the title goes **under** the photo (y=780–900 of 1688 device px), so the hero plus its words take the whole first screen, and the dozen starts below the fold. `Hero.svelte:114-118` (phone) and default grid `:28-35`
5. The play mark is a 44 px brown disc (`--photo-shade-55`), not glass. `Hero.svelte:76-87`
6. Two Hero blocks (On this day + Rediscover, both on by default) would stack as two identical layouts. Nothing makes the first one lead. `routes/home/+page.svelte:207-242`
7. The cover is `previewOf()`, a client rewrite of `/thumb` → `/preview`. It works, but it is the URL rewrite the Collections spec warns against. `lib/home.ts:161-165`

### Flight spec: `MemoryHero` (variant of `CollectionHero`)
| | Laptop | Phone |
|---|---|---|
| Frame | **Full-bleed** 1440 wide, height `min(78vh, 720px)` (≈ 21:10 at 1440×900), `object-fit: cover`, 0 radius, under the floating top bar. | **Edge to edge, 4:5** (390×488) under the status bar. With the date overlay it fills the first screen down to the dock, with the dozen peeking. |
| Crop | `object-position` from a focus point: faces on the photo when the API gives them (see H1), else `50% 40%` (people's heads sit high). | Same. |
| Type on the photo (bottom-left, 32 / 16 px inset, over `--scrim-photo`) | `.eyebrow` **"REDISCOVER · 18 SEP 2021"** (On this day: "ON THIS DAY · 2019"). Then the title **"Five years ago"** at `--fs-display` 56/700. Then the note 15/500 at 80 % white ("Lisbon", or "Lisbon, with Sam and Léa"). | Eyebrow the same, title 40/700 (2 lines max), note 15. |
| Play | A glass capsule bottom-right: an **ink pill "▶ Play"** plus the photo count in 13 tabular ("12"). One pill, not a disc. | A 44 px glass circle bottom-right, level with the title baseline. |
| Tap | Anywhere on the photo plays the story (as now). With the keyboard, the hero is one button whose name is "Play: Five years ago" (as now). | Same. |
| Drift | **Ken Burns**: `transform: scale(1.0 → 1.08) translate(±2%)` over 24 s, ease-in-out, alternate. The drift moves toward the focus point. It pauses when off screen (IntersectionObserver) and on `prefers-reduced-motion`. | Same, 20 s. |
| Scroll | A scroll-driven animation (`animation-timeline: scroll()`): the photo moves at 0.5× (parallax) and dims to 50 %. The date and eyebrow fade out by 40 % scrolled. | Same. |
| Second hero | When both On this day and Rediscover are on, only the **first** in the account's order is the lead. The other becomes a **wide CoverCard** (21:9 laptop / 3:2 phone, 28 px radius, in the content column) with the same eyebrow and title on the photo at 34/700. | Same, 3:2. |

### The dozen (Rediscover's other 11)
Problem: a justified grid with an orphan last row, at 2 px gutters right under the hero, so it reads as part of the Library rather than as picks. `routes/home/+page.svelte:233-241`

Spec: a **Rail** of photo CoverCards directly under the hero, with no section header (the hero is its header).
- Laptop: 3:2 cards at 4.3 visible, so (1376 − 4×16)/4.3 ≈ **305×203**.
- Phone: 4:5 cards at 2.3 visible, so (358 − 2×12)/2.3 ≈ **145×181**.
- Each card has its year as an eyebrow on the photo ("2016").
- A tap opens the Loupe stepping through the dozen (the current `open('rediscover', id)` keeps working). A press scales to 0.96.

---

## 3. Memories

### What is wrong, ranked
1. On laptop, 15 rem cards (240 px) show 5.7 cards across 1376 px. The sixth card is cut flat at the page padding, so nothing peeks past the edge. `MemoryRow.svelte:113-116`
2. Captions sit under the photo (16/700 title + 14 line). `MemoryRow.svelte:87-94`
3. The play disc is on every card. `MemoryRow.svelte:22`
4. The cover is the 640 px thumb (`memory.cover.thumb.url`), which is fine at 240 px but soft at the Flight sizes below on a 2× screen. `MemoryRow.svelte:19-21`

### Flight spec
- A Rail of **CoverCards**: 3:2 at 3.3 visible on laptop, so (1376 − 3×16)/3.3 ≈ **402×268**; 4:5 at 1.3 visible on phone, so (358 − 12)/1.3 ≈ **266×333**.
- On the photo: an eyebrow with the dates ("4–8 SEP 2026", or "39 PHOTOS" for a month at home; this is `memoryLine`), then the title at 22/650 ("Carnac, September 2026").
- No play disc. Hover (laptop) scales the image 1.03 and deepens the scrim. On laptop, glass ‹ › arrows appear on hover.
- The cover uses the preview URL from the API (see H2), or `previewOf` until then.

---

## 4. Years

### What is wrong, ranked
1. The year is a 16/700 caption **under** a small square (176 px laptop, 152 px phone), when it should be the hero of the tile. `MemoryRow.svelte:107-120` (`small`)
2. A play disc on every tile (eight in one row). `MemoryRow.svelte:22`
3. The header "Years ›" links to `/` (the Library unfiltered), so the chevron promises a Years page that does not exist. `routes/home/+page.svelte:248`
4. The rail has the same flat cut as Memories (problem 0.4).

### Flight spec: `YearTile`
| | Laptop | Phone |
|---|---|---|
| Rail | 4:5 tiles at 5.3 visible: (1376 − 5×16)/5.3 ≈ **244×305**. | 4:5 at 2.3 visible: **145×181**. |
| Numeral | **"2019" at 64/700, tabular, tracking -0.03em**, bottom-left on the photo over `--scrim-photo`. This is the Tesla spec number. Above it, the eyebrow "26 PHOTOS". | 40/700 numeral. |
| Tap | Plays the year's story. The year's photos are a laptop's ⋯ on hover, or a phone's long-press menu, which opens "Show in Library" → `/?from=YYYY-01-01&to=YYYY-12-31` (the filters already parse it: `lib/filters.ts`). | Same. |
| Header | "Years" 22/650 with no chevron (there is no page). | Same. |

---

## 5. Pinned

### What is wrong, ranked
1. **Home asks for up to 200 pinned photos and lays them all out** in a justified grid. A family that pins a lot gets an endless block in the middle of Home. `routes/home/+page.svelte:41,73-75,256`
2. Ragged last row (problem 0.3).
3. "Choose ›" links to `/`, not to the pinned photos. `routes/home/+page.svelte:254`

### Flight spec
- A Rail of photo cards at the photo's **true aspect at a fixed height**: 220 px on laptop, 160 px on phone, gap 4, 12 px radius. This is a strip, so there is no orphan and no crop.
- Fetch 24, not 200. A trailing "See all N" card (`--fill`, 15/600) opens `/?pinned=true`.
- The header has "Pinned" 22/650 and a trailing "See all" (15 `--ink-2`) that goes to the same place. "Choose" goes away: pinning is done in the Library and the Loupe.
- Unchanged: the Loupe steps through the pinned photos, and Pinned reloads after the Loupe closes (`:157-160`).

---

## 6. People

### What is wrong, ranked
1. Four 76 px circles are packed left with about 1000 px empty on laptop. `routes/home/+page.svelte:258-270,340-359`
2. On phone, four bubbles fill exactly 390 px, with no peek and no "more".

### Flight spec
Reuse the Collections People row as it is: **FaceBubble**.
- Laptop: an 8-col grid, gap 24, giving **151 px** circles.
- Phone: a Rail of 76 px bubbles at 4.4 visible, bleeding to the screen edges.
- Each bubble has the name 15/600 and the count 13 `--ink-2`. The header is "People ›" to `/people`.

---

## 7. New this week

### What is wrong, ranked
1. The sentence "30 photos arrived from Old hard disk." is a paragraph under the heading, adding a third line before the photos. `routes/home/+page.svelte:273,333-336`
2. Ragged justified grid of 12 (problem 0.3).

### Flight spec
- Header "New this week" 22/650. The sentence becomes a 13 `--ink-2` subline under it ("30 photos from Old hard disk"); `arrivalsSentence` stays, without the trailing period.
- The photos are the same strip as Pinned (true aspect, fixed height). The trailing card "All 30" goes to the Library.
- "All photos ›" stays as the header's "See all".

---

## 8. Empty, loading and error

| State | Today | Flight |
|---|---|---|
| Loading | A flat block 58 % wide plus a rail of 3 blocks. `routes/home/+page.svelte:199-203` | **Skeleton** in the real shapes: a full-bleed hero block (4:5 phone, `min(78vh,720px)` laptop) with an eyebrow bar and a title bar where the type will go, then one rail of `n.3` cards. 1.2 s shimmer (transform on a gradient). The first rendered photo fades in over 200 ms; the date shows at once, since it needs no data. |
| Library empty | Two paragraphs with links. `:279-295` | **EmptyState**: a 64 px photo glyph, "No photos yet" 17/600, one 15 `--ink-2` line, and the primary pill "Upload photos" (plus "Add a folder" for the admin). |
| Nothing chosen has content today | "Your story starts here." + a paragraph. | EmptyState: "Nothing on Home today", then the pill "Choose what Home shows" → You (`/settings#home`) and a quiet "Pin photos in the Library". |
| Error | A text block with Try again. `:192-197` | EmptyState with the error in plain words and the pill "Try again" (as now). |

Motion on the page: blocks enter staggered once per visit (40 ms each, opacity plus an 8 px rise). Cards press to 0.96 for 100 ms. Rails use scroll snap. The hero → story move is a shared element (§9).

---

## 9. Story player

### What is wrong, ranked
1. **Every photo is letterboxed** (`object-fit: contain` on `--bg`). On a phone a landscape photo is a 390×220 band with about 600 px of grey above and below it (the screenshot). It feels like a viewer, not a Memories movie. `StoryPlayer.svelte:265-275`
2. The title sits in a **glass box** (`--r-2`, 16 px padding) rather than set on the photo. On laptop it is a small brown card bottom-left; on phone it is a full-width slab. `StoryPlayer.svelte:219-222,364-387`
3. Rediscover's story is titled **"Rediscover"** while its hero said "Five years ago". `routes/home/+page.svelte:128`
4. The push-in is always a scale from the centre (1 → 1.06), so every photo moves the same way. `StoryPlayer.svelte:288-295`
5. It opens with a plain fade (`story-open`). The hero the person tapped does not grow into the player. `StoryPlayer.svelte:242-248`
6. The progress segments sit on the grey letterbox at `--lens` contrast. They are fine on photos and invisible on light skies. `StoryPlayer.svelte:322-337`
7. The chrome (Pause, ×) never hides, and at the end the story just closes. There is no "Play again". `StoryPlayer.svelte:91-98,356-362`

Kept as is (it works): the clock in `lib/story.ts`, hold-to-pause, tap zones (⅓ back / ⅔ next), pull-down to close, Back closes, prefetch of the next two, and pause while hidden.

### Flight spec: a full-screen glass experience
| | Laptop | Phone |
|---|---|---|
| Stage | True black. A photo whose orientation matches the screen is shown **full-bleed** (`cover`). One that does not match is shown whole (`contain`) over a **backdrop of itself**: the 640 px thumb scaled to cover, `blur(40px) saturate(1.4)`, dimmed to 45 %, so there are never grey bars (Apple Memories). | Same. On a portrait phone a landscape photo is whole and centred over its own blurred backdrop. |
| Motion per photo | **Ken Burns with direction**: each photo gets one of four pans (zoom-in toward the focus point, zoom-out, pan left, pan right), picked from its index so it is stable, scale 1.0–1.10 over `PHOTO_MS + fade`. Cross-dissolve 600 ms. Transform and opacity only. | Same. |
| Open | A **shared element**: the tapped hero or card `<img>` gets `view-transition-name: story-cover` and grows into the stage over 420 ms `cubic-bezier(.32,.72,0,1)`. The chrome fades in after. | Same. |
| Close | × or Escape reverses into the card (the name is set again on the card it came from). A pull-down scales the stage with the finger (to 0.85 at 300 px), rounds its corners to 28 px, and on release past `shouldClose` flies home to the card; otherwise it springs back. | Same; the pull is the main way. |
| Title | **On the photo**, bottom-left over `--scrim-photo`, with no box: the eyebrow "REDISCOVER · 2012–2026", then the title at `--fs-display` 56/700 ("Five years ago"). It shows for the first 3 s, then shrinks to the eyebrow alone (opacity + transform). | Eyebrow + 40/700 title, 16 px inset, above the home indicator. |
| Progress | Segments of 2 px, white at 35 % / 100 %, over a top scrim `linear-gradient(to bottom, rgb(0 0 0 / .4), transparent 120px)` so they read on any sky. | Same, below the status bar. |
| Chrome | Glass circles (Pause, ×) top-right. They **fade out after 2.5 s** and come back on pointer move, focus, or pause. On a laptop the cursor hides with them, and glass ‹ › appear at the edges on hover. Space toggles pause. | Fade out after 2.5 s. A long press shows them (and pauses, as today). |
| End | It does not close. An **end card** cross-fades in over the last photo, dimmed: the title, then the ink pill "Play again", a glass "Show in Library" (the story's filter), and ×. | Same, stacked. |
| Reduced motion | No drift and no shared element: a plain 200 ms cross-fade. The running segment shows whole, as now. | Same. |

---

## 10. You → "Home shows, in this order" (`OrderList`)

### What is wrong, ranked
1. **Move up is a chevron `^` button on every row but the first.** It reads as "collapse this row", not "move". Moving New this week to the top takes six taps. `ui/OrderList.svelte:47-49,32-37`
2. There is no drag. The UI direction asks for motion first and things that follow the finger, and iOS users reorder by dragging a handle.
3. The switch is a white track with a black knob when on. It reads as off, or as a light-mode control in a dark page. `ui/OrderList.svelte:50-57` (styles in `fields.css`, slice 6)
4. Rows are 62 px with a hairline gap and no section icons, so seven identical grey bars give no sense of what each block looks like.
5. "On this day" is on but shows nothing today (the mock has none), and nothing in the list says so. The owner cannot tell an empty block from a broken one.
6. On laptop the list is a 640 px column with 760 px of black to its right. `routes/settings/+page.svelte:127-137` (and the page column, covered in admin-settings-auth.md)
7. `animate:flip` runs 240 ms on Svelte's default ease, not a spring. `ui/OrderList.svelte:22-25,45`

### Flight spec: `SortableList` (replaces `OrderList`, also used by the admin look form's Collections rows, `admin/LookForm.svelte:189,221`)
| | Laptop | Phone |
|---|---|---|
| Groups | Two glass groups: **"Shown"**, in order, and **"Not shown"**. Switching a row off moves it, with a spring, to the top of "Not shown"; switching it on appends it to "Shown" (today's rule: `toggle`). The last shown row cannot be switched off (as now). | Same. |
| Row | 56 px: a 28 px rounded-square **section glyph** (sun for Rediscover, calendar for On this day, stack for Memories, "19" numeral for Years, pin, face, sparkle for New), then the name 17/500, then a quiet 13 `--ink-2` hint when the block is empty today ("Nothing today"), then the switch, then the **grip ≡** at the far right. | Same; the hit area is the full row height. |
| Drag | The **grip** starts a drag at once with the pointer. The row lifts (scale 1.03, `--lift`, glass), follows the pointer 1:1 on the y axis, and the other rows **spring aside** (`lib/spring.ts`, stiffness 350, damping 30; FLIP with transform only). On drop it springs into its slot and saves (`chooseHome`, as now). | A **long-press of 350 ms anywhere on a shown row**, or a touch on the grip, picks the row up. The list auto-scrolls near the edges. Vertical drag is locked, so the page does not scroll under the finger (`touch-action: none` on the grip only). |
| Keyboard and screen reader | The grip is a button, "Reorder Years". Space picks up, ↑/↓ move, Space drops, Escape cancels. A live region says "Years, 3 of 6". Move up and Move down also stay in the row's context menu, so nothing depends on dragging. | VoiceOver: "Move up" and "Move down" as two visually-hidden buttons in each row, which appear on focus. Do not rely on custom rotor actions. |
| Laptop room | The list is in the left column of the two-pane settings layout (admin-settings-auth.md). The right pane shows a **live mini Home**: grey block shapes in the chosen order (hero, rail, tiles), which re-flow with the same spring as you drag. | No preview. |
| Switch | The Flight switch: track `--fill`, which turns `--accent` when on (this is a selection), with a white knob that slides on a spring. Slice 6. | Same. |

Empty hint data: the settings page already has `api.home()`, so "Nothing today" needs no backend change.

---

## 11. Add-to-Home-Screen tip (`InstallTip.svelte`)

### What is wrong, ranked
1. The text "how" is 12 px (`--fs-12`). It is the only instruction and is hard to read on a phone. `InstallTip.svelte:100-104`
2. It rises over the Rediscover dozen at `--motion-sheet` and covers the bottom third of the first screen, while the person is still taking in the hero. `InstallTip.svelte:50-64`
3. It is dismissed only through ×. There is no swipe, unlike every other glass sheet.
4. Its glass is the old 74 % recipe (problem 0.1 of the plan).

### Flight spec
- The Flight glass card (62 % + 24 px blur, 0.5 px edge, 28 px radius), floating 8 px above the dock, max 26 rem (as now).
- Title 15/600. The steps 13/500 `--ink-2` with inline ink icons (as now, larger). The app icon is 44 px with a 10 px radius.
- It appears **once the hero has drifted for 4 s, or on the first scroll**, with a spring rise (scale 0.96 → 1, 12 px rise). It never covers the lead hero's title.
- A **swipe down** dismisses it (spring, through the `sheet-drag` helper), as well as ×. It is gone for good either way (`install.close()`, as now).
- Laptop and tablet: never (as now, `lib/install-tip.ts`).

---

## 12. iOS status bar in the app (standalone) with the light look

**Fact:** `app.html:12` sets `apple-mobile-web-app-status-bar-style` to `black-translucent`. The page draws under the status bar and iOS draws the clock and battery **white**. That meta is the only switch, and iOS reads it when the app is added or launched; changing it from script while the app runs is not known to work. The other value, `default`, gives a dark clock on a solid white bar but stops the page from drawing under it, which kills full-bleed heroes. So in the light look, the clock stays white over a light page and is unreadable. (Test on a real iPhone before relying on any runtime switch; no doc says one works.)

**Flight handles it by never putting a light surface under the status bar:**
1. **Home, album, person, and story** start with a full-bleed photo under the status bar. Every such hero gets a **top scrim**, `linear-gradient(to bottom, rgb(0 0 0 / .45), transparent calc(env(safe-area-inset-top) + 64px))`, so white text always reads, in both looks. This is the same scrim that carries the date (§1).
2. **Every other page in light look and standalone** gets a fixed **status-bar plate**: a strip `height: env(safe-area-inset-top)` with a gradient from `rgb(0 0 0 / .55)` to `rgb(0 0 0 / .25)`. It sits above the glass top bar, which starts under it. It shows only when `(display-mode: standalone)` matches, or `navigator.standalone`, and the look is light. In a Safari tab the inset is 0, so the plate is invisible.
3. `theme-color` becomes `#000000` in dark and stays `#000000` in light for standalone. Safari tabs can follow the look, but standalone has no effect on the clock.
4. Rejected: switching to `default`. It keeps a white bar that never collapses, and the glass top bar can no longer slide under it.

A test: the style guard checks that the meta stays `black-translucent` (`install-tip.spec.ts:141`). Add an e2e test (phone, light, standalone emulated as in `screenshots.spec.ts` "on an iPhone") that the plate is visible on `/collections` and absent on `/home` (because the hero scrim covers it).

---

## 13. Shared components (names match the other area specs)

| Component | On Home | Notes |
|---|---|---|
| **CollectionHero** → `MemoryHero` variant | Lead hero (§2) | Adds the top date overlay, the play pill instead of ActionCapsule, a focus-point crop, and the Ken Burns drift. Same scroll collapse and same `view-transition-name` hook. |
| **CoverCard** | Second hero (wide), dozen, Memories, "See all" end card | Adds `aspect="21/9"` and a `variant="photo-strip"` (true aspect, fixed height) for Pinned and New. |
| **YearTile** | Years | A CoverCard with a numeral slot (64/40, tabular). Could also serve a Library "Years" zoom level later. |
| **Rail** | Dozen, Memories, Years, Pinned, People (phone), New | `visible` = 4.3 / 3.3 / 5.3 / 2.3 / 1.3, bleed to the screen edges, glass ‹ › on hover, keyboard arrows. |
| **FaceBubble** | People | As in Collections. |
| **SectionHeader** | Every block but the lead hero | 22/650 title, an optional chevron link, "See all", and an optional 13 `--ink-2` subline (New this week). Replaces `HomeSection`. |
| **Skeleton**, **EmptyState** | §8 | As in Collections. |
| **StoryPlayer** (restyled) | §9 | Keeps `lib/story.ts`. Adds a backdrop layer, directional Ken Burns, an end card and chrome auto-hide. |
| **SortableList** | You → Home, admin look Collections rows | Replaces `OrderList`. Built on `lib/spring.ts` (slice 2). |
| **StatusPlate** | Shell (`+layout`) | §12. |

---

## 14. Backend / API needs (and the ones that are not needed)

| # | Need | Why | Change |
|---|---|---|---|
| H1 | **Focus point per cover** (the biggest face box centre, or one saliency point) | Full-bleed 21:10 and 4:5 crops of arbitrary photos will cut heads; the Ken Burns drift needs a target. | Add an optional `focus: {x, y}` (0–1) to `AssetOut`, or only to the covers in `HomeData` (contract change; faces already exist server side). Fallback: `50% 40%`. Owner decision. |
| H2 | **Preview URL in the API** for covers (`on_this_day.cover`, `rediscover[0]`, `memories[].cover`, `years[].cover`) | Heroes and 402 px cards on 2× screens need more than the 640 px thumb. Today `previewOf` rewrites the URL in the client (`lib/home.ts:161-165`). | Add `preview: {url}` beside `thumb` on `AssetOut` (contract change; same as Collections B1). Fallback: keep `previewOf`. |
| H3 | Blur-up placeholder | The hero and story fade in from black. | Same as the plan's thumbhash item (schema). Fallback: the skeleton + fade. |
| no | Pinned "See all" | `/?pinned=true` is already parsed (`lib/filters.ts:10`). | none; fetch 24 instead of 200 (client). |
| no | Year "Show in Library" | `from`/`to` filters exist. | none |
| no | "Nothing today" hints in You | `api.home()` from the settings page. | none |
| no | Story end card "Show in Library" | `Memory.filter` / `OnThisDay.filter` already carry it. Rediscover has no filter, so it offers only "Play again". | none |
| no | Home sections storage | Per-account `homeSections` in the look sheet (#83). | none |

Cross-area touches to call out in PRs:
- `PageHead`/shell: the hero runs under the bar, plus the status plate (slice 3).
- `fields.css` switch (slice 6).
- `OrderList` → `SortableList` is also used by `admin/LookForm.svelte` (the admin area).
- `themes.css` `--bg` and `theme-color` (slice 1).

## 15. Slice

Home becomes **slice 10** in the plan's table: it runs after slices 1 (tokens), 2 (spring), 3 (shell) and 6 (switch), and in parallel with 7 and 8. It owns `routes/home`, `components/home/*`, `InstallTip`, `ui/OrderList` → `SortableList`, and the status plate in `+layout`.

Risks:
- **Medium:** e2e `home.spec.ts` asserts the Play buttons and the section names. Keep the accessible names, so the tests change on purpose, not by accident.
