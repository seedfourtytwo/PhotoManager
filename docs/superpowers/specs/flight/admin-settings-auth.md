# Admin, Settings, Auth, Review, Trash — review + Flight spec (2026-10-15)

Scope: `/settings` (You), `/admin` (status, folders, backups, search & faces, people, look form,
look trial, stop watching, problems), devices + token, `/login` (account picker + 4-digit PIN; there
is **no password** anywhere), `/setup`, `/review`, `/trash`. Target: `../design-system.md`.
Paths below are under `web/src/`. Screenshots: `review/raw/{desktop,phone}-{14,14b,14c,15,16,16b,22,23,01,02,02b}*.png`.

## 0. Cross-cutting problems (fix once, every screen here gets better)

| # | Problem | Where |
|---|---|---|
| 1 | Every page is a 40rem column pinned left; at 1440 the right ~780px is empty. | `routes/admin/+page.svelte:221-226`, `routes/settings/+page.svelte:166-169`, review/trash grids |
| 2 | Raw machine errors are the headline ("repository not reachable: connection refused (is the server on?)"), shown on You *and* Admin, bold, wrapping 3 lines on phone. | `lib/backups.ts` `backupSentence` → `problems[0].message`; `admin/+page.svelte:127-133`; `settings/+page.svelte:117-121`; `Backups.svelte:129-136` |
| 3 | Rows are separated by 2px seams of page colour = visible lines; group surface is `--raised` grey on a non-black page. Flight: true black, no lines. | `lib/utilities.css:184-193` (`gap: var(--fine)`), `.tile-row` `:198-212` |
| 4 | Sheets are `--raised` cards with Cancel/Close as plain text at the **bottom**; on tall sheets (Look form) the actions scroll off-screen (desktop-22 shows no Save at all). No glass, no sticky header. | `components/Dialog.svelte:35-38, 42-56` |
| 5 | "ActionCards" (icon-over-word tiles, 5–6 per sheet) wrap 3+2 on phone, all equal weight; primary action not distinguished from Disable. | `admin/ActionCard.svelte`, `Backups.svelte:154-183`, `Sources.svelte:212-253`, `Users.svelte:192-221` |
| 6 | Native `<select>` and checkboxes everywhere a segmented control or switch belongs. | `Users.svelte:143-149,181-191`, `Sources.svelte:255-267`, `LookForm.svelte:118-138,190-200,241-251`, `Devices.svelte:161-166` |
| 7 | Bottom padding `--s-7` < dock height: last group sits under the phone dock (People hidden in phone-14, a review section in phone-review). | `admin/+page.svelte:225`, `review/+page.svelte:150`, `trash/+page.svelte:223` |
| 8 | Data font with slashed zero used for human numbers (PIN pad "0", "30 days", "02:30", sizes) → reads as code. | `PinPad.svelte:44`, `--font-data` uses |
| 9 | Status colours exist (`--ok`, `--fail`) but Flight's palette defines none, and the accent is amber — a warning amber would collide with "accent = selection/focus only". | `design-system.md` colour table |
| 10 | Errors drawn as a 2px ink rule + text (`p[role=alert]`), no icon, no recovery action. | `login/+page.svelte:242-252`, `setup/+page.svelte:112-117` |

**Plain-language rule for this whole area** (status, errors, toasts): *headline* (what happened, ≤6 words, no jargon) + *one line* (what to do / what it means) + optional **Details** disclosure holding the raw text, path, repository or job id. Example: "Last backup didn't finish" / "The home server didn't answer. Check it's switched on, then tap Back up now." / Details: `repository not reachable: connection refused`. Numbers in words where small ("Two places", "1 photo couldn't import").

---

## 1. Settings shell (You + Admin become one place)

**Now:** You (`/settings`) and Admin (`/admin`) are two stacked full pages with a text back link under the top bar; avatar opens a page, not a popover; Admin is one row inside You (`settings/+page.svelte:123-129`); Admin is one 1000px-tall scroll of 5 groups.

**Flight spec**
- **Laptop (≥1024):** two-pane like macOS System Settings. Left: sticky glass sidebar 260px (`--glass`, 28px radius, 16px from top-bar, 32px from left), large-title "Settings" 22px, then sections as `SidebarItem` (icon in 28px `--fill` rounded square + word, sliding lens on active, spring 350/30). Sections: **You**, **Appearance**, **Phones**; separator gap 24px; admin-only: **Overview**, **Folders**, **Backups**, **People**, **Search & faces**. Right: content column max 680px centred in the remaining width (Overview may use 960px bento). Each section = its own URL (`/settings/folders`…) so back/forward and deep links (`#a-backups` today) work.
- **Tablet 640–1023:** sidebar collapses to icon rail 72px.
- **Phone:** iOS grouped-inset root list (large title 34px that shrinks into a glass nav bar on scroll); each section pushes a page (view-transition slide 380ms sheet curve, swipe-from-edge back). Back = glass circle chevron top-left + title, never a text link under the bar.
- **Avatar (top bar / dock):** laptop → glass popover 320px anchored to avatar: profile header, Appearance segmented, "Needs you" row if any, Settings…, Sign out. Phone → pushes Settings root.
- Motion: section switch on laptop = content cross-fade + 8px rise (200ms); rows press-scale 0.98.
- Loading: skeleton rows (same height, `--fill` shimmer off by reduced-motion). Error loading a section: inline EmptyState "Couldn't load folders" + Retry.

## 2. You / Settings root

**Now (ranked)**
1. Left-pinned 40rem, big dead right (`settings/+page.svelte:166`).
2. Admin's raw backup failure repeated as "Needs you" for the admin (`:117-121`) — duplicate of Admin, scary wording.
3. Profile = grey disc with initial + h1 "C" (`:98-104`); no visual weight, no photo.
4. Mode segmented is 60px-tall icon-over-word with "Like the device" (`:106-115, 196-209`).
5. Sign out is a normal row next to Change PIN, no destructive tone (`:135-137`); version "Library server mock" floats at the bottom (`:140`).

**Flight spec (You section)**
- Profile header card (not a list row): 72px Avatar, name 22/650, role as quiet line ("Admin"). Laptop: card spans the 680 column; phone: centred like iOS Apple ID header.
- **Appearance:** `SegmentedControl` Dark · Light · Auto (word "Auto", sub-caption "Follows this device"), 36px, sliding lens on spring. Larger text toggle lives here if/when the look sheet exposes it.
- **Needs you** (only when something does): one `StatusRow` with StatusPill "Needs you" + headline ("Last backup didn't finish") → Backups. Max one row; plural collapses to "2 things need you".
- **Account:** Change PIN (→ PIN flow, §4); Sign out as a centred destructive-tone row at the bottom of its own group (iOS style).
- Footer: "Photos · server 1.8.2" 13px `--ink-3`, centred.

## 3. Phones (devices, token, keep-on-phone)

**Now (ranked)**
1. Token screen: token in a text input, "Copy" as an underlined link, shown-once warning as body text (`Devices.svelte:169-180`).
2. Setup steps are a dense numbered list with arrows and a raw `POST http://127.0.0.1:5183/api/upload`, plus repo paths `docs/guides/*.md` the partner can't open (`:181-195`).
3. Kind chosen by native select (`:161-166`); revoked phones stay listed forever (`:95-96`).
4. Device sheet mixes quiet stats line, tile groups, a raw checkbox switch and a danger tile (`:130-151`, `DeviceKeeps.svelte:64-121`).

**Flight spec**
- List: `SettingsRow` per phone, icon by kind, detail "iPhone · used 2 hours ago", trailing StatusPill only when revoked/never used. Revoked collapse into "Revoked (2)" disclosure. Empty: EmptyState "No phones yet" / "A phone can send its new photos here by itself." / [Add a phone].
- **Add a phone = 3-step sheet (`StepFlow`)**, sticky header with step dots:
  1. Name field + `SegmentedControl` iPhone · Android · Computer · Other. Primary "Create".
  2. **Token card**: `CopyField` large (token in 15px mono, one line, ellipsis middle), primary pill "Copy token" → morphs to "Copied ✓" (spring scale 0.96→1). Callout: "Shown once. If you lose it, remove this phone and add it again."
  3. **Set up on iPhone**: numbered step cards (glass, 20px radius) each with one short instruction and the value to paste as a `CopyField` (URL `{origin}/api/upload`, header value `Bearer …`). Raw guide paths removed; "Full guide" only if docs are served by the app (they aren't — see API flags).
- Device page (push, not dialog): header (icon, name, kind, added, last used, last synced) → "Keeps" / "Leaves off" grouped lists with swipe-to-remove on phone, ✕ button on hover laptop → `Switch` "Leave out screenshots" → row "Send everything again" → destructive "Remove this phone" (ConfirmSheet: "It stops uploading now. To use it again you'll add it again.").

## 4. PIN flows (Change PIN, Reset PIN for someone, Add person PIN, Setup PIN)

**Now:** two bare PIN text fields, no confirmation of the new PIN — a typo locks you out (`settings/+page.svelte:144-162`); admin reset is one field (`Users.svelte:160-171`).

**Flight spec:** one `PinEntry` component (PinDots + Keypad on touch, typed on laptop) used in a stepped sheet: "Enter current PIN" → "New PIN" → "Again". Dots advance on spring; mismatch = shake (transform only, 380ms) + "Those didn't match. Try again." Success: sheet closes, toast "PIN changed. Other devices are signed out." (server already ends other sessions — `auth.py change_pin`).

## 5. Admin — Overview (status + problems/jobs)

**Now (ranked)**
1. Status = 3 identical rows; the one thing that matters (backup failed) is a red 10px dot + 3 lines of raw error (`admin/+page.svelte:126-142`).
2. Library row isn't tappable and is just "299 photos, 412 GB free" (`:134`).
3. Problems sheet shows `job.kind` + "photo 123" + raw error + attempts (`:172-194`) — engineer log.
4. Search & faces row title is the state ("Not set up yet") (`:148-155`); the sheet tells the user to run `just models` (`:204`).

**Flight spec**
- **Laptop:** bento of 3 `StatusCard`s across 960px (Backups wide 2/3, Library 1/3; Problems full row only when >0). Each card: 11px caps eyebrow ("BACKUPS"), headline 22/650 in plain words ("Protected in 2 places" / "Last backup didn't finish"), one line, StatusPill top-right, primary action inline when relevant ("Back up now"). **Phone:** same cards stacked full-width, 20px radius, then grouped list of sections.
- Library card: big tabular numeral "299" + "photos", line "412 GB free". Storage bar only if API adds totals (flag A4). Tap → Library.
- Problems page: grouped list, each row = thumbnail 44px (if `asset_id`) + plain headline from a kind→words map ("Preview couldn't be made", "Couldn't read photo") + quiet "Tried 3 times · next try in 10 min" + trailing "Retry" text button; Details disclosure shows raw `error`. Header action "Retry all". Empty: "Nothing's wrong" with check glyph.
- Live: while jobs run, a slim glass `ProgressCapsule` floats bottom-centre (above dock on phone): "Importing · 42 photos so far" with an indeterminate shimmer (no total known, A11); determinate only for ML analysis (`ml.counts`). Replaces silent polling (`Poller` stays).
- Search & faces: row title "Search & faces", StatusPill "On" / "Off"; page explains in one line + ProgressRow from `ml.counts` + primary "Analyse remaining photos". Not-installed copy: "Needs a one-time install on the server. Ask C." — the `just models` command goes inside Details.

## 6. Admin — Folders (+ folder page, Stop watching)

**Now (ranked)**
1. Row line overloaded and contradictory: "198 photos, last import 199 new, 1 failed, 2 skipped, checked 28 Sept 2026, 21:14" — wraps to 2 lines on phone (`Sources.svelte:181`, `lib/folders`).
2. Header actions are unlabeled icons (refresh + plus) floating at the group label's far right (`:170-175`).
3. Folder sheet: monospace path first, 5 ActionCards of equal weight, then a native select for recheck (`:207-270`).
4. Stop-watching sheet is good copy; primary "Stop watching" is the white primary even when "Move them to the trash" is picked (`StopWatchingDialog.svelte:105`).

**Flight spec**
- Section header: large title "Folders" + glass pill buttons "Check all" (icon+word) and "Add" (menu: Folder on this computer · Proton Drive · Cloud folder).
- Row: icon (folder/cloud) · title · detail **one** short line: "198 photos · checked 2 h ago"; trailing StatusPill when relevant ("Importing · 42 so far", "1 problem", "Paused"). Full import counts move to the folder page.
- Folder page (push): header (name 34px, quiet path in 13px with Details for full path); **one** primary pill ("Check now" / "Pull now"), then grouped list: Last import (→ Report) · Who sees it · Check by itself (`SegmentedControl` Off · Hourly · Daily · Weekly) · next check line · Pause (Switch "Watch for new photos") · destructive "Stop watching…" at the bottom.
- Stop watching: ConfirmSheet (laptop centred 480px, phone bottom sheet). Keep `ChoiceList` (radio rows). Button label follows choice: "Stop watching" / "Stop and trash 87 photos" in destructive tone. Counting state: skeleton row "Counting photos…" with disabled button. "No longer watched" group stays, as a disclosure under Folders.

## 7. Admin — Backups

**Now (ranked)**
1. Status line = comma chain with raw error, bold (`Backups.svelte:129-136`): "overdue, last backup 25 Sept 2026, 02:31, failed: repository not reachable…".
2. "Only 0 of 1 places up to date" (`:107-110`) — awkward with zero.
3. Schedule in engineer format "daily 02:30, only 22:00-06:00" + repository path in code (`:133-136, 152`).
4. Six equal ActionCards per place (`:154-183`); Recent runs as a 3-column table (`:185-201`); state as dot/ring/diamond shapes (`:257-277`).
5. Whole thing in a 36rem dialog over Admin.

**Flight spec**
- Own section/page. Top: **hero StatusCard** — big headline "Protected in 2 places" / "Not protected yet" / "Last backup didn't finish", one line, primary "Back up now".
- Each place = card: name + StatusPill (Up to date · Offline · Needs you · Running with spinner), headline in words ("Backed up 2 hours ago", "Hasn't backed up since Thursday"), quiet line "Every night at 2:30 · 48 GB". Restore proof as a sub-row "Restore tested 3 days ago ✓" / "Restore never tested" (pill). Proton copy sub-row same pattern. Recovery key not saved → in-card callout with button "Save recovery key".
- Actions: primary "Back up now"; secondary row of glass round icon buttons with labels underneath (max 3: Test restore · Recovery key · More…); More = menu (Copy to Proton, Pause, Details). Disable is never a peer of Back up now.
- Recent runs: `RunList` rows (status glyph · "Backup · 25 Sep, 02:31" · result words · Details).
- Running: card shows determinate/indeterminate bar; the pill pulses (opacity, 1.2s) — reduced-motion: static.
- Empty: EmptyState "No backups yet" / "Your photos exist only on this computer. Adding one takes a minute." / [Add backup].

## 8. Admin — People (accounts)

**Now (ranked)**
1. Generic person icon, not an avatar; detail "Admin, you" (`Users.svelte:117-124`).
2. Person sheet = native role select + 3–4 ActionCards (Look, Reset PIN, Unlock, Disable) (`:177-222`).
3. Add person: 4 stacked fields incl. a native role select and PIN text field (`:127-158`).
4. On phone the whole group is under the dock (cross-cutting #7).

**Flight spec**
- List: Avatar 36px (initial on `--fill`) · name · detail role ("Member") · trailing pills "You" / "Locked" / "Off". Header "Add" glass pill.
- Person page: Avatar 72 + name + username (13px quiet). Grouped: Role (`SegmentedControl` Admin · Member · Guest, caption under: "Guests can view and download"); Look → (§9); Reset PIN → PinEntry sheet; Unlock (only when locked, with line "Locked after too many wrong PINs"); `Switch` "Can sign in" (replaces Disable/Enable; hidden for yourself). Optimistic role change, rolls back with toast on refusal (logic exists, `patch`).
- Add person: StepFlow — Name + username → Role segmented → PIN (PinEntry ×2) → done screen "Give Léa her PIN in person."

## 9. Look form + Look trial

**Now (ranked)**
1. 28rem dialog, ~1400px tall; Save/Try buttons below the fold (desktop-22 ends at "Reset look") (`LookForm.svelte:112, 274-285`; `Dialog.svelte:48`).
2. Each dial = checkbox "The theme's own" + disabled slider + raw value "200°" (`:141-172`); hue shown as a number, no swatch.
3. Native selects for theme, mode, photo size, opens-on (`:118-138, 190-200, 241-251`); "Move up" text buttons for ordering (`:217-224`).
4. Trial banner: full-width strip with ink left rule, pushes the page down; on phone wraps to 2 lines over the title and has no Save (`LookTrial.svelte:7-24`, phone-23).

**Flight spec**
- Laptop: **split view** sheet 960px — left 420px controls (scroll), right live preview (scaled mini Library + Collections using the sheet's tokens). Phone: full-height sheet with large detent, controls only; "Try on my screen" is the preview.
- Sticky sheet header: Cancel · "Look for Partner" · Save (primary). Footer-less.
- Controls (grouped list): Theme `SegmentedControl` (theme names — see flag A10); Mode Dark·Light·Auto; Accent = `SliderRow` with a hue-gradient track + swatch thumb and an "Auto" chip that toggles theme default (replaces checkbox+disabled slider); Corners, Gap, Text size = `SliderRow` (value shown "12 px", "100%" in UI font, Auto chip); Photo size S·M·L segmented; Collections rows = `ReorderList` (drag handle, switch per row, last one can't switch off); Home: Switch "Show Home" + segmented "Opens on Home·Library" (disabled with reason line when Home off); Phone: Switch "Labels under dock icons". "Reset to default" destructive-quiet row at the bottom.
- **Trial banner** → floating glass capsule top-centre (under top bar; on phone above dock): "Previewing Partner's look" · [Back to edit] · [Stop]. Never reflows the page. Enters on spring from -12px.
- Loading: skeleton rows; save error: inline callout at top of sheet.

## 10. Login (account picker + PIN)

**Now (ranked)**
1. Laptop layout is not centred — content starts at x=528, everything left-aligned in a column (`login/+page.svelte:72-114`; `.touch` centring only for coarse pointers `:226-241`).
2. Laptop PIN = four 12px dots inside an amber focus pill; no pad, no hint you can type (`:143-166`).
3. Flat grey page, wordmark "Photos" in title voice, avatars are initials on `--tint` (`:116-122, 202-212`).
4. Pad: "Delete" as a word, slashed-zero digits (`PinPad.svelte:13-19, 44`).
5. Error = left-ruled text; lockout/429/network not differentiated in wording.

**Flight spec**
- True-black full-screen, everything centred on both sizes. Ambient background: slow-drifting soft gradient blobs (transform only, 30s loop), **not library photos** (pre-auth screen on the LAN — privacy, see A2).
- Picker: "Who's looking?" 22/650; Avatars 96px (laptop) / 84px (phone) in a centred row, name under (15/500). Hover lift (scale 1.04 + `--lift`); press 0.96.
- Choose → **shared-element morph**: chosen avatar flies to top-centre (72px), others fade; PinDots (14px, 20px gap) + Keypad (78px round glass keys, `--fill`, digits Inter 32/400 non-slashed, ⌫ icon, "Cancel" bottom-left like iOS). Laptop shows the same Keypad (clickable) *and* accepts typing; caption "Type or tap your PIN".
- 4th digit auto-submits (exists); dots pulse while checking. Wrong PIN: shake + dots clear + "Wrong PIN". 429: "Too many tries. Wait a moment and try again." 423: "This account is locked. Ask C to unlock it." Network: "Can't reach the library — is the home server on?" + [Try again]. "Someone else" = glass pill bottom.
- Success: dots fill accent, screen scales 1.04 + fades into Home (300ms).

## 11. Setup (first admin)

**Now:** left-pinned form (`setup/+page.svelte:50-76`); "Welcome" in weight 350 vs login's 700 (`:79-82`); "User name" vs "Your name" confusing; PIN typed in plain fields twice; left-aligned button (`:107-111`); success drops you on an empty library.

**Flight spec:** centred 3-step `StepFlow`, same ambient background as login, step dots top. (1) "Welcome to Photos" display 40/700 + one line "Let's make your account. You'll add everyone else later." → field "Your name" (display name) with username auto-derived and editable under Details ("Sign-in name: c"). (2) PinEntry "Choose a 4-digit PIN" → "Again". (3) "You're in" → primary "Add your first folder" (→ Settings › Folders › Add) / quiet "Later". Errors inline under the field in plain words.

## 12. To review

**Now (ranked)**
1. Thumbnails letterboxed in 4:3 `object-fit: contain` boxes with grey bars (`review/+page.svelte:200-207`); grid 10rem/20rem left-packed, desktop 70% empty (`:169-174`).
2. Look-alike pairs too small to compare (~170px each); captions "New 4032 × 3024" in data font (`:64-67`).
3. Paragraph lede before content (`:79-82`); last section under phone dock.
4. Keep/Move-to-trash pill pairs per group are fine but are the only path for whole groups; single-photo decision is a small dialog (`:126-146`).

**Flight spec**
- Large title "To review" + count; lede becomes a one-line subtitle.
- **Look-alikes:** `CompareCard` per pair — laptop: two photos side by side at true aspect, ~45% width each, labels on photo scrim bottom-left ("New" / "Already in library"), spec chips under each ("4032×3024 · 12 MP" with the larger one marked "Larger"); actions under the pair: primary "Keep both", destructive-quiet "Don't import". Phone: swipeable 2-up carousel per pair with the same actions; cards stack vertically.
- **Clutter groups** (Screenshots, Receipts, Documents): justified grid (2px gutters, no letterboxing) with section header + "Keep all" / "Trash all" glass pills; tap a tile → Loupe-style viewer with bottom bar Keep · Trash; long-press/Select for multi-select → SelectionBar Keep · Trash.
- Decided items animate out (scale 0.9 + fade, grid reflows with FLIP). Toast with Undo is **not** possible for keep (see A9) — show plain confirmation.
- Empty: EmptyState "All caught up" / "Look-alikes, screenshots and documents found while importing wait here." Loading: skeleton grid.

## 13. Trash

**Now (ranked)**
1. On load the first tile gets an amber focus outline and a visible select circle (`trash/+page.svelte:85-86` `refocus()` focuses a tile; desktop-15/phone-15) — looks selected.
2. "Restore all" / "Empty trash" hidden in a ⋯ menu (`:43-47, 142`); phone header has 3 circles + avatar crowding.
3. Empty state is a bare sentence (`:153-155`); lede paragraph (`:148-151`).
4. Delete-for-good confirm uses the white primary button (`:216`).

**Flight spec** (iOS "Recently Deleted")
- Large title "Trash" + subtitle "Photos are removed for good after 30 days. Your original files are never touched."; header: glass pill "Select". Grid = the Library justified grid; each tile has a small glass badge bottom-left "12 d" (red-tinted under 3 days).
- Not selecting: bottom glass bar (laptop: floating capsule) "Restore all" · "Delete all" (admin only). Selecting: SelectionBar "Restore" · "Delete" with count.
- Delete confirm = destructive action sheet: "Delete 3 photos for good?" / plain consequence line / red "Delete for good" + Cancel.
- Restore animates tiles out (scale + fade), toast "Restored 3 photos". Fix focus: only refocus when the focused element was removed (logic change, not visual).
- Empty: EmptyState with trash glyph "Trash is empty".

---

## 14. Shared components to build once

| Component | Used by | Notes |
|---|---|---|
| `SettingsShell` (+ `SidebarItem`) | §1 | two-pane laptop / push-stack phone; per-section URLs; sliding lens |
| `GroupedList` | §2–9 | one continuous surface (`--raised` on black), 20px radius, **no separators** — 52px rows give rhythm; optional header label (13px `--ink-2`) + footer note |
| `SettingsRow` | everywhere | icon in 28px `--fill` rounded square (monochrome; one-accent rule) · title · detail · value · trailing = chevron \| Switch \| button \| pill \| none · tone default\|destructive · href/onclick · loading skeleton |
| `StatusPill` | rows, cards | shape + word + colour: Up to date / Running / Offline / Needs you / Paused / Locked / Off; never colour alone |
| `StatusCard` | Overview, Backups | eyebrow caps, headline 22, line, pill, one inline action |
| `SegmentedControl` | Appearance, role, recheck, kind, look | sliding lens on spring (350/30), 36px (44 touch), icon optional |
| `Switch` | pause folder, can sign in, look toggles, screenshots | iOS toggle, thumb on spring |
| `SliderRow` | Look | label, value text, optional "Auto" chip, custom track (hue gradient variant) |
| `ReorderList` | Look rows | drag handle + keyboard up/down |
| `PinDots` + `Keypad` → `PinEntry` | login, setup, change/reset PIN, add person | typing + tapping, shake on error, auto-submit at 4 |
| `Avatar` | login, You, People | initial now; portrait later if A1 lands |
| `Sheet` (replaces `Dialog`) | all sheets | glass over scrim, sticky header (Cancel · Title · Done/primary), grab handle + detents on phone, centred 560/720/960 panel on laptop, rises on 380ms sheet curve |
| `ConfirmSheet` | stop watching, delete for good, revoke, remove phone | destructive variant, label states the consequence |
| `StepFlow` | setup, add phone, add person, add backup | step dots, back, sticky primary |
| `CopyField` | device token, upload URL, recovery key | big readable value, Copy → Copied ✓ morph |
| `Disclosure` ("Details") | every raw error/path/command | collapsed by default |
| `ChoiceList` | stop watching, kind pickers | radio rows w/ description (pattern exists in `StopWatchingDialog`) |
| `RunList` | backups runs, problems | status glyph · when · words · Details |
| `ProgressCapsule` | import/backup/analysis | floating glass, determinate when counts known |
| `EmptyState` | review, trash, phones, backups, problems | glyph · title · line · optional action |
| `FloatingNotice` | look trial, "needs you" toast | glass capsule, never reflows layout |
| `CompareCard` | review look-alikes | two photos, scrim labels, spec chips |

New tokens needed in `design-system.md`: `--ok` (e.g. `oklch(0.78 0.15 150)`), `--fail` (`oklch(0.68 0.2 25)`); warnings use ink + weight, not amber, so the amber accent stays selection/focus only.

## 15. Needs backend/API change — don't design in without it

| # | Want | Gap |
|---|---|---|
| A1 | Faces/photos as account avatars (login, People) | `AccountName`/`User` have no picture or person link (`lib/api/types.ts:12-36`). Also a pre-auth portrait endpoint would show family faces to anyone on the LAN — recommend initials stay on Login even if added elsewhere. |
| A2 | Library photo as login background | Same privacy problem; don't. Ambient gradient only. |
| A3 | Lockout countdown ("try again in 4:32") | Login returns 401/423/429 (`backend/.../routes/auth.py:44-50`); verify a retry time is in the body/`Retry-After` before designing a countdown. |
| A4 | Storage bar (used vs free) on Library card | `Stats` has only `free_bytes` (`types.ts:135-141`); needs `library_bytes` + `total_bytes`. |
| A5 | Plain-language backup headlines | `BackupProblem.message` / `BackupRun.error` are raw tool text. Needs an `error_kind` enum (unreachable, disk_full, auth, locked, unknown) — pattern-matching strings on the client is fragile. |
| A6 | Plain-language job names | `Job.kind` is an internal string; a client map is fine if kinds are a closed set — confirm the list. |
| A7 | People "last signed in" / sessions list | Not in `ManagedUser`. |
| A8 | QR code for the device token / one-tap Shortcut install | QR needs a new dependency (hard stop: `TECH_DECISIONS.md`); a downloadable `.shortcut` needs the server to build/serve it. The `docs/guides/*` the sheet mentions aren't served by the app. |
| A9 | Review "Replace library photo with the new one" / Undo after Keep | API only has keep (both stay) and discard; no replace, no un-keep. |
| A10 | Flight-only theme (retire Safelight/Album) | Theme list is the look-sheet contract mirrored from `backend/domain/look.py`; changing it is a contract change. |
| A11 | Import progress as % / "42 of 199" | `ImportRun.summary` counts what is done (`files_seen`, outcomes) but has no expected total (`types.ts:86-96`); show running count + indeterminate bar unless a total is added. |
