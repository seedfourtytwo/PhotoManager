# Features

Priorities: **M1–M6** refer to milestones. **✅** = built and tested. in [`ROADMAP.md`](ROADMAP.md).
**Must** = the milestone fails without it. **Should** = planned, can slip one milestone.
**Could** = nice, only if cheap. **Later** = explicitly out of scope for v1.

Target library for v1: **< 10,000 photos**, a handful of accounts, one laptop (Ubuntu, 15 GB RAM,
RTX 2070 Max-Q 8 GB). Every design choice must also hold at 100k so the home-server move is boring.

---

## 1. Collect (ingestion)

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 1.1 | Import a local folder (recursive), **read-only** on the source | Must | M1 ✅ |
| 1.1a | **Multiple source folders**, each registered once with a label (e.g. "Laptop Pictures", "Old HDD", "Partner's export"); all aggregated into the one de-duplicated library; "rescan all" picks up new files from every source | Must | M1 ✅ |
| 1.1d | **Pick a folder by browsing** the machine's folders in the web app (admin, read-only listing; the library's own folder is never offered) | Must | ✅ |
| 1.1e | **Automatic re-check** per source (folder, cloud, Proton): off / every hour / day / week, set on Admin → Folders, which also shows the next check. It queues the same read-only check as "Check again"; a failed check waits for the next interval | Should | ✅ |
| 1.1b | **Remote folders** as sources: anything rclone can reach read-only — SFTP/SSH (e.g. the home server), SMB/NAS share, WebDAV, plus MEGA/Proton (1.6). Same staging → import path | Should | M4 |
| 1.1c | Per-source view: how many photos came from each source, overlap between sources, last scan, errors | Should | M2 |
| 1.2 | Supported formats: JPEG, PNG, HEIC/HEIF, WebP, TIFF, GIF, AVIF ✅; common RAW recognised, decoding to verify in M2 with real RAW files; Live Photo video halves detected and reported ✅ | Must | M1 |
| 1.3 | Content hash (BLAKE3) → exact duplicates are stored once, all source paths remembered | Must | M1 ✅ |
| 1.4 | Resumable, idempotent import: re-running an import changes nothing | Must | M1 ✅ |
| 1.5 | Import report: new / duplicate / skipped / failed, with reasons | Must | M1 ✅ |
| 1.6 | Cloud sources via rclone: **MEGA** and **Proton Drive** pulled into a staging folder, then imported like 1.1 | Should | M4 |
| 1.7 | iPhone source: USB/Wi-Fi pull with libimobiledevice, or iCloud export folder | Should | M4 |
| 1.8 | Android source: pull over wireless ADB | Could | M4 |
| 1.9 | Watch folder: new files in a drop folder get imported automatically | Could | M5 |
| 1.10 | Videos (catalogue + thumbnail only) | Later | — |

**Copy on connect (always on):** the moment a source is connected, every photo in it is copied
into the library on whatever machine runs the app (laptop now, server later). The source is
never changed or deleted. This is deliberately *not* optional: sources disappear (a cloud
account lapses, a phone gets wiped, an old disk dies) and the library must survive that.
At < 10k photos that is roughly 30–60 GB — cheap insurance. A "reference only" mode for huge
archives is a Later item, not v1.

**Hard rule:** sources are mounted/opened read-only; the library keeps its own copy under
`library/originals/YYYY/MM/<hash>.<ext>`. Deletion inside the app is a soft "hide" plus a
separate, explicit "purge from library copy" that never touches the source.

## 2. Understand (metadata & enrichment)

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 2.1 | EXIF/XMP/QuickTime metadata via ExifTool: capture time (with timezone repair), camera, lens, GPS, orientation | Must | M1 ✅ |
| 2.2 | Date fallback chain: EXIF → XMP → filename pattern (`IMG_20190704_…`) → file mtime; each photo records *which* source won | Must | M1 ✅ |
| 2.3 | Thumbnails (fit 640 px, made during import from the source file, which also proves the file decodes) and previews (fit 2048 px, background job), orientation-corrected WebP via libvips | Must | M1 ✅ |
| 2.4 | Offline reverse geocoding (country / region / city) — no network call | Should | M2 ✅ (API) |
| 2.5 | Near-duplicate & burst detection (perceptual hash + time window), "pick the best" helper — *pHash + time-window groups done in the API; "pick the best" helper to do* | Should | M2 |
| 2.5b | **To review** (issue 8): a newly imported photo that looks like one already in the library, or that the auto-tagger sees as a screenshot, document, receipt or meme, is copied in but held out of the library. A grouped review screen offers Keep (joins the library, never held again) or Discard (30-day trash). Applies to every source | Should | M2 ✅ |
| 2.6 | Quality signals: blur, exposure, eyes-closed (from face landmarks) → used for "best of" picks | Could | M3 |
| 2.7 | Semantic embeddings (CLIP-family) for every photo | Must | M3 |
| 2.8 | Face detection + clustering into people; user names clusters; merge/split; **hide** a person you do not want listed (a stranger in the background): they leave People, their faces stay grouped so they do not come back as a new "Someone", and a "Hidden" list brings them back (issue 53) | Should | M3 |
| 2.9 | Auto-tags from embeddings against a fixed vocabulary (beach, snow, food, document, screenshot…) | Should | M3 ✅ (API) |
| 2.10 | Screenshot / document / meme detection → filtered out of "memories" by default | Should | M3 |
| 2.11 | Captions from local vision LLM (via AI socket) | Could | M5 |
| 2.12 | **Fix dates**: set or shift the date of one or many photos (e.g. Facebook downloads whose only date is the download day); the photo shows "date guessed from file" until fixed; corrections are kept in the library and exported with XMP (11.2). The exact date is a text field that takes a date or time pasted in any common format (the app's own, ISO, camera, file name, English or French month names, month-first, AM/PM) and always shows it day first on the 24-hour clock | Should | M2 ✅ (API) |

## 3. Find (organise, filter, search)

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 3.1 | Timeline (newest first), grouped by day/month/year, fast scroll with the time ruler | Must | M2 |
| 3.2 | Facet filters: date range (From / To take a pasted date like Fix date and show it day first), place, camera, people, tags, favourite, media kind, source — *API: date, place, camera, favourite, source, guessed date, location; people/tags in M3* | Must | M2 |
| 3.3 | Favourites (per user) and hide (per user) | Must | M2 ✅ (API) |
| 3.4 | Keyword search over places, tags, names, captions — *API: file names, places, camera, album titles; tags/names/captions in M3* | Must | M2 |
| 3.5 | Natural-language search ("kids in the snow at grandma's") via embeddings | Should | M3 ✅ (API) |
| 3.6 | "More like this" similar-photo search | Should | M3 ✅ (API) |
| 3.7 | Smart collections = saved filters (e.g. "France house, summer") | Should | M3 |
| 3.8 | Private items: hidden from everyone who reaches them only through the marker's own folders (the marker, and people with access through other folders, still see them) | Should | M2 ✅ (API) |

## 4. Look (views)

Each view is a way to *see* the library, not decoration. See `DESIGN_PRINCIPLES.md`.

| # | View | Prio | Milestone |
|---|---|---|---|
| 4.1 | **Justified grid** — rows of true-aspect thumbnails, no cropping | Must | M2 |
| 4.2 | **Loupe** — single photo, true full screen (Fullscreen API), previous/next by **keyboard** (← → , Esc closes, F toggles fullscreen, I toggles info), **swipe** on touch, and **two discrete edge buttons** that fade after 2 s of no movement; preloads neighbours so stepping is instant; metadata in a quiet side margin | Must | M2 |
| 4.3 | **Calendar heat map** — years × days, ink = number of photos; click a day to open it | Should | M2 |
| 4.4 | **Map** — clustered points, draw-to-filter | Should | M3 |
| 4.5 | **Small multiples** — one row per year for the same week/place ("every summer at the house") | Could | M3 |
| 4.6 | **People** — face grid, then a person's timeline | Should | M3 ✅ (API) |
| 4.7 | **On this day** — same date, previous years | Could | M3 |
| 4.8 | **Slideshow / ambient mode** for a TV or tablet | Could | M5 |

## 4b. Download & convert

The library lives on the laptop now and the server later; any device that opens it can pull
copies down.

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 4b.1 | Download one photo from the loupe (original file) | Must | M2 ✅ (API) |
| 4b.2 | **Multi-select download**: selected photos → one streamed ZIP (no temp file on the server) | Must | M2 ✅ (API) |
| 4b.3 | **Bulk scopes**: whole day / month / year, an album, a person, or "everything matching the current filter"; shows count and size before starting — *API: ids, album or any filter, with estimate* | Must | M2 |
| 4b.4 | **Format**: Original · JPEG (quality slider) · PNG · WebP; HEIC → JPEG is the common case — *API done in M2* | Should | M3 |
| 4b.5 | **Resize on export**: presets (Original, 4K long edge, 2048, 1080, "email" 1280) or custom long edge; never upscale — *API done in M2* | Should | M3 |
| 4b.6 | Options: strip GPS/location, keep or strip all metadata, file naming (`date_place_###` or original name), folder structure in ZIP (flat / by year / by month) — *API done in M2* | Should | M3 |
| 4b.7 | Phone: single photos use the share sheet (Web Share API) so they can go straight into the iPhone Photos app; multiple → ZIP to Files | Should | M3 |
| 4b.8 | Large exports run as a background job with progress and a "ready" link, resumable if the connection drops | Could | M4 |
| 4b.9 | Standalone converter: drop files in, get them back converted/resized (without importing them) | Could | M4 |

## 4c. Basic editor (non-destructive)

Edits are stored as a small **recipe** (JSON) per photo, shared by everyone who may edit it (api-v1); the original is never changed.
Views and downloads render the recipe on the fly (and cache the result). "Revert" deletes the recipe.
Leaving the editor with changes that are not saved (Back, Escape or Cancel) asks first: Keep editing or Discard changes.

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 4c.1 | Rotate 90°/180°, flip — *recipe + render API done in M2* | Must | M3 |
| 4c.2 | Crop: free or fixed ratio (1:1, 4:5, 3:2, 16:9, print sizes), straighten ±15° — *recipe + render API done in M2* | Should | M3 |
| 4c.3 | Resize (as part of export, 4b.5) | Should | M3 |
| 4c.4 | Light & colour: exposure, contrast, highlights/shadows, saturation, warmth; one "auto" button | Could | M5 |
| 4c.5 | Black & white, a few calm presets (no Instagram-style filter zoo) | Could | M5 |
| 4c.6 | Save as copy: bake the recipe into a new asset linked to its original | Could | M5 |

**Recommendation for v1:** rotate + crop + resize are cheap with libvips and give most of the
value — ship them in M3. Colour adjustments look simple but carry a real cost: the browser
preview (canvas/WebGL) and the server export (libvips) must produce the *same* result, which
needs its own golden-image tests. Park them for M5 and decide then.

## 5. Albums

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 5.1 | Manual albums: select → add, reorder by drag, cover photo, title, description | Must | M2 ✅ (API) |
| 5.2 | Shared albums between the two users; each album has an owner and collaborators | Must | M2 ✅ (API) |
| 5.3 | Album **theme**: typography, colour palette, paper tone (a small curated set) | Should | M4 |
| 5.4 | Album **layout engine**: pages built from layout templates (full-bleed, 2-up, 3-grid, hero+2, text page) with automatic best-fit by aspect ratio | Should | M4 |
| 5.5 | Page editor: swap photo, change layout, pan/zoom crop inside a frame, captions | Should | M4 |
| 5.6 | "Suggest an album" without AI: by event (time + place clustering) | Should | M4 |
| 5.7 | **Describe an album in words** → LLM returns a structured album plan (selection query, order, sections, layouts, captions) that the user reviews and edits | Should | M5 |
| 5.8 | AI-generated decorative graphics (title pages, ornaments) through the socket | Later | M6+ |

## 6. Print

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 6.1 | Export album to print-ready PDF (Typst): chosen trim size, 3 mm bleed, safe-area guides, embedded fonts | Should | M4 |
| 6.2 | Resolution check: warn when a photo would print below 200 ppi at its frame size, block below 150 | Should | M4 |
| 6.3 | Presets: A4 / A5 landscape & portrait, 20×20 cm square, US Letter | Should | M4 |
| 6.4 | Single prints & contact sheets | Could | M4 |
| 6.5 | Print-service specific presets (e.g. a specific lab's spec) | Later | — |

## 7. AI socket (optional)

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 7.1 | A single `AIProvider` port with a **Null** implementation shipped by default — the app is complete without AI | Must | M1 ✅ |
| 7.2 | Ollama adapter (base URL + model names in settings; works against laptop or home server) | Should | M5 |
| 7.3 | Capabilities: `caption(photo)`, `plan_album(prompt, library_summary) → AlbumPlan (JSON schema)`, `explain_search(query)` | Should | M5 |
| 7.4 | Every AI output is a **proposal**: shown as a diff the user accepts, edits or discards | Must | M5 |
| 7.5 | Photos never leave the network the user configured; AI calls logged locally | Must | M5 |

## 8. Accounts & access

Any number of accounts. Access is granted **per source folder** (and per album), so a
folder can be shared with everyone, with a few people, or kept to one person.

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 8.1 | Account system: any number of local accounts; roles **admin** (manages accounts, sources, backups) and **member**; optional **guest** (view/download only, no upload/edit) | Must | M2 ✅ (API) |
| 8.2 | **Per-source access**: each source folder has an access list (everyone / chosen accounts / only its owner) with a level: view, view+download, edit | Must | M2 ✅ (API) |
| 8.3 | Access rule: you see a photo if you can see *any* source it came from, or it is in an album shared with you. (A photo found in both an open and a restricted folder is therefore visible — the UI warns about this when you restrict a folder.) | Must | M2 ✅ (API) |
| 8.4 | Albums shared per account with viewer/editor roles, independent of folder access | Must | M2 ✅ (API) |
| 8.5 | Per-user favourites, hidden, private items, recent views, edit recipes — *API: favourites, hidden, private, edit recipes; recent views later* | Must | M2 |
| 8.6 | Each account's phone inbox is its own source, private to that account by default | Should | M4 |
| 8.7 | Remote access via Tailscale (no public exposure) | Should | M6 |
| 8.8 | Account groups (e.g. "family", "friends") to grant access in one go | Could | M4 |
| 8.9 | **Per-account look**: each account has a look (theme, dark/light/device mode, accent hue, corners, photo gap, text size, photo size, which Collections rows in which order, dock labels) stored as a validated sheet of values, never CSS. The account chooses its mode in Settings; an admin sets the rest (the photo size too: there is no per-device setting for it) in Admin → People → Look, with "Try on my screen" before "Save for …". The two Today switches are stored but wait for the Today page | Should | ✅ |

## 9. Operate

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 9.1 | One-command dev start; one-command production start | Must | M1 ✅ |
| 9.2 | Background job queue (survives restarts, retries, failed jobs keep their reason) ✅; visible progress in the UI in M2 | Must | M1 |
| 9.3 | Backup — see §9b | Must | M6 |
| 9.4 | Docker Compose deployment for the home server, same code | Should | M6 |
| 9.5 | Integrity check: re-hash originals, report bit-rot or missing files | Could | M6 |

## 9b. Backup (incremental, scheduled)

The library is the one place everything ends up, so it gets its own backups — separate from
the sources, which we never rely on. **Built in M6** (decided 2026-09-29); the design is
fixed now so nothing in M1–M5 makes it harder (data folder layout, DB snapshot hook).

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 9b.1 | Backup targets: a local folder / external disk, a network folder (SMB/NAS, SFTP to another machine), or any rclone cloud remote; more than one target allowed | Must | M6 |
| 9b.2 | **Incremental**: only new/changed data is sent; deduplicated and versioned snapshots | Must | M6 |
| 9b.3 | Schedule per target: hourly / daily / weekly / manual, with a quiet time window | Must | M6 |
| 9b.4 | Covers originals + edit recipes + albums + a consistent database snapshot (thumbnails are rebuildable and skipped) | Must | M6 |
| 9b.5 | Encrypted at rest on the target (password kept outside the library) | Should | M6 |
| 9b.6 | Retention: e.g. keep 7 daily, 4 weekly, 12 monthly snapshots | Should | M6 |
| 9b.7 | Status page: last success per target, size, next run; warning banner when a backup is overdue or failed | Must | M6 |
| 9b.8 | One-click **restore test**: restores a random sample to a temp folder and verifies hashes (also part of every QA session) | Should | M6 |
| 9b.9 | Full restore guide (new machine → working library) — tested once per milestone | Should | M6 |
| 9b.10 | **Guided setup in the web app**: pick a disk, folder or cloud remote; space check; the app makes the key and insists on a saved copy; first backup starts at once | Must | ✅ |
| 9b.11 | **Proven restores**: an automatic restore test after the first backup and every week; a failed proof raises the banner | Must | ✅ |
| 9b.12 | **Off-site copy on Proton Drive** (issue 14): a local backup is also copied, encrypted, to a Proton Drive folder after every run, through Proton's own CLI (no Proton password in the app); a failed copy raises the banner; restore steps in the backup guide | Should | ✅ |
| 9b.13 | **A place that is not connected is skipped, not failed**: an unplugged disk or unreachable remote is recorded as "skipped", the other places still run, it is looked for again every 15 minutes and backed up when it returns (at once if overdue, otherwise in its quiet window); a repository is never re-created for a place that has had a successful backup | Must | ✅ |
| 9b.14 | **Two-places rule**: a place is an enabled backup target or the Proton Drive copy of one; "protected" means at least two places are up to date; the Backups page says "Protected in 2 places" or "Only 1 of 2 …" and lists one row per place | Must | ✅ |
| 9b.15 | **Warning banner on every page** for admins when the library is not protected or a place needs attention; it cannot be dismissed and goes when the problem is fixed. No alert outside the app yet (email/phone) | Must | ✅ |

## 10. Web and phone app

Two clients, clear split of jobs:

- **Web (any browser, laptop or phone):** browse the library on the server, search, albums,
  edit, and download copies to whatever device you're on. No installation, nothing synced.
- **Phone app (installed; parked, see 10.5):** the full product — every feature the web has, same screens,
  same behaviour — *plus* automatic sync between the phone and the server. The app is the
  main way to use it on a phone; the web is the fallback when you can't or don't want to install.

Without the app there is no automatic sync: the server can't reach into a phone and pull
photos, and on iPhone a web page can't run in the background or read the photo library by
itself. The phone has to push, and only an installed app can do that on its own.

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 10.1 | Web: browse, search, albums, edit, download/save to device — works on laptop and phone browsers | Must | M2 |
| 10.2 | Web: **hand-picked upload** from any device (phone: pick from the Photos library; laptop: pick files or a folder) into your inbox | Must | M2 |
| 10.3 | Server side of sync: per-user inbox + upload API (resumable, "which of these hashes do you already have?", per-device tokens) | Should | M4 |
| 10.4 | **Free automatic iPhone upload via Apple Shortcuts** (built into iOS, no app, no cost): a personal automation — e.g. "when charging" or "every night" — finds photos added since the last run and posts them to the upload API. We ship the shortcut + a setup guide. Needs a spike first: batch-size limits and whether it runs without a tap on current iOS | Should | M4 |
| 10.4b | **Partner's iPhone via Proton**: her phone backs up to Proton, we pull from Proton. Done through Proton's own `proton-drive` CLI (issue 8): the Photos section, the whole Drive or one folder; the sign-in stays in Proton's tool. Still to do: timed re-checks | Could | M4 ✅ (manual pull) |
| 10.5 | **Own phone app** — full web feature parity + background sync. Parked: an iPhone app needs the paid Apple Developer Program ($99/yr) or re-signing every 7 days with a free Apple ID | Later | — |
| 10.6 | Phone app: server → phone sync ("keep this album on my phone") | Later | — |
| 10.7 | Phone app: free-up-space helper | Later | — |

**Laptop:** no app and no sync. Once the server exists, the laptop is just a browser. New
photos from the laptop go in by web upload (10.2) or by adding a folder as a source.

## 11. Cross-cutting (added by the gap check, 2026-09-29)

| # | Feature | Prio | Milestone |
|---|---|---|---|
| 11.1 | **HTTPS on the home network.** iPhones only allow installing the web app, full screen, the share sheet and offline caching over HTTPS. Use Tailscale's free HTTPS certificates (MagicDNS name like `photos.<tailnet>.ts.net`); fallback: Caddy with a local certificate authority | Must | M2 |
| 11.2 | **No lock-in:** everything we know about a photo (date fixes, tags, people, favourites, albums, captions) can be exported as XMP sidecar files next to the originals plus one JSON dump; downloads can include XMP | Should | M3 |
| 11.3 | **Trash:** deleting from the library moves to a 30-day trash (per user for hidden/private, admin for library copies); never touches sources | Must | M2 ✅ (API) |
| 11.4 | **Disk guard:** import pauses with a clear message when free space on the data disk drops below a threshold (default 10 GB) | Must | M1 ✅ |
| 11.5 | **Logs and errors you can read:** structured logs to `data/logs/`, rotated; failed jobs visible in the UI with the reason and a retry button | Must | M1 ✅ |
| 11.6 | **Safe upgrades:** the database is snapshotted automatically before every schema migration | Must | M1 ✅ |
| 11.7 | **Laptop-friendly:** image-processing concurrency is a setting (default 2 threads) ✅; ML jobs run niced (M3) | Must | M1 |
| 11.8 | **iPhone file quirks:** `IMG_E1234` (edited copies) grouped with their original, `.AAE` edit files ignored, Live Photo `.MOV` halves paired and hidden until video support | Must | M1 ✅ |
| 11.9 | **Videos in sources:** counted and reported as "skipped: video (not supported yet)" instead of silently ignored | Must | M1 ✅ |
| 11.10 | **Account safety:** no public sign-up (admin creates accounts), login rate limiting per account (10 wrong PINs: wait 15 minutes; 30: locked until an admin unlocks it), session expiry, 4-digit PIN login and PIN change | Must | M2 ✅ (API) |
| 11.11 | Share link for someone without an account (expiring, view-only, one album) — only over Tailscale Funnel or similar; decide when needed | Later | — |
