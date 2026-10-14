# Performance

Measured on the development machine (2 cores, Linux, SQLite 3.45.1) with **synthetic data
only**: the QA libraries built by `scripts/make_mock_library.py` (~2000 imported mock photos)
plus synthesised rows — 10,695 and 51,336 photos, 4 users (admin, two members, a guest), 6
sources with mixed access lists, albums with members, favourites and private photos. "Before" is
the integrated M2 code (`a26a04e`), "after" is `fix/backend`; both ran back to back on the same
copies of the same libraries (median of 9 runs).

Reproduce: `uv run python scripts/perf/bench_repo.py <library.db> 9` (repository level, on a
copy) and `uv run python scripts/perf/import_e2e.py <folder>` (import + previews until idle).

## Library queries (ms, median of 9)

Timeline = first page of 200, newest first. Columns: admin / member (alice) / member (bob) / guest.

| 10k photos | before | after |
|---|---|---|
| timeline 200 | 35 / 29 / 28 / 16 | **4.0 / 4.7 / 4.7 / 5.3** |
| year=2019 | 28 / 22 / 21 / 14 | 4.1 / 4.9 / 10 / 10 |
| year + month | 29 / 21 / 19 / 13 | 2.6 / 3.1 / 2.1 / 0.5 |
| favourite | 23 / 24 / 21 / 8.5 | 0.0 / 8.4 / 4.9 / 0.0 |
| source_id=2 | 35 / 29 / 27 / 18 | 5.8 / 8.7 / 7.8 / 7.1 |
| q=lisbon | 47 / 39 / 53 / 30 | 14 / 28 / 21 / 37 |
| facets | 149 / 117 / 112 / 53 | **28 / 42 / 46 / 30** |
| calendar | 30 / 25 / 23 / 11 | 13 / 21 / 24 / 22 |
| map | 39 / 29 / 27 / 12 | 17 / 25 / 29 / 22 |

| 50k photos | before | after |
|---|---|---|
| timeline 200 | 163 / 128 / 122 / 62 | **3.9 / 4.7 / 4.8 / 5.2** |
| year=2019 | 149 / 102 / 92 / 54 | 4.1 / 4.8 / 5.4 / 6.7 |
| year + month | 133 / 96 / 105 / 46 | 4.1 / 5.0 / 5.6 / 2.6 |
| favourite | 138 / 108 / 90 / 45 | 0.0 / 20 / 13 / 0.0 |
| source_id=2 | 164 / 142 / 116 / 62 | 11 / 46 / 12 / 12 |
| q=lisbon | 218 / 180 / 154 / 83 | 56 / 124 / 87 / 74 |
| facets | 795 / 622 / 575 / 284 | **173 / 262 / 245 / 154** |
| calendar | 163 / 134 / 112 / 55 | 46 / 97 / 99 / 92 |
| map | 196 / 154 / 136 / 65 | 94 / 146 / 152 / 123 |

What changed (C25–C27): the visibility rule is per-photo correlated SQL (an `EXISTS` decides
*whether*, the level is only computed for returned rows) instead of a CTE over the whole
library, so a page stops at its `LIMIT` on the new partial index `asset_live_timeline`; admins
skip the access lists; year/month are `taken_at` ranges; "only my favourites" starts from
`user_asset`; facets are one grouped scan plus one per-source count instead of five scans;
`ANALYZE` after migrations, `PRAGMA optimize` every 6 h. Reads run on per-thread WAL
connections, so they no longer queue behind the writer (C26). Guests got slower on full-library
aggregates (calendar/map ~55 → ~95 ms at 50k): the old rule was cheap for someone who sees
little, the new one checks every photo — still far inside the budget at 10k.

Budget check (ARCHITECTURE §5, 10k photos): *filter change < 200 ms p95* — every filter,
facets, calendar and map are ≤ 50 ms at 10k (≤ 270 ms even at 50k).

Transport (C30): `/api/map` for 41,447 points is 2,439 KB of JSON → **146 KB** gzip-encoded
(level 6); the shape is unchanged. Hashed web build files are cached for a year.

## Grouping (bursts and near-duplicates, 51,336 photos)

| | before | after |
|---|---|---|
| `group_shots` over the whole library | 9.1 s | **0.32 s** (identical output) |
| group job after an import of 100 new photos | full regroup (≈ 9.5 s + 51k row updates) | 0.43 s: one run of 131 photos regrouped |

Times and perceptual hashes are converted to ints once; new photos only regroup the runs of
time they land in (no group spans a gap longer than the 10-minute window). Date fixes, trash and
restore queue one full regroup (≈ 0.8 s).

## Job queue and purge indexes (migration 0022)

Synthetic rows on the development machine (SQLite 3.45.1, median of 200, disk flush excluded
with `synchronous = OFF`): 40,000 finished jobs, 10,000 queued previews, 50,000 photos. "Before"
is `f7898a4`.

| ms | before | after |
|---|---|---|
| poll of the long lane (nothing of its kinds waiting) | 1.84 | **0.035** |
| poll of the quick lane (nothing of its kinds waiting) | 2.51 | **0.034** |
| quick lane claims a job queued behind the 10k previews | 2.71 | 0.19 |
| preview pool claims the next preview | 0.04 | 0.13 |
| `enqueue_once("geocode")` while one is waiting | 1.29 | **0.033** |
| `enqueue_once` of a kind with 10k waiting jobs of that same kind | 1.62 | 2.82 |
| `GET /api/stats` job counts (50k job rows) | 2.67 | 4.43 |
| purge one trashed photo (`purge_asset`) | 19.8 | **8.7** |
| … of which: clear variants (`variant_of = ?`) | 6.3 | 0.008 |
| … of which: foreign-key check of `DELETE FROM asset` | 6.0 | 0.04 |
| … of which: clear look-alikes (`held_like = ?`, no index) | 7.4 | 7.8 |

What changed: the partial index `job_waiting (kind, id) WHERE status = 'queued'` and a claim
statement that lists the kinds with waiting jobs by index seeks, then takes the oldest due job
of the lane's kinds — a poll no longer walks the other lanes' queue. `asset_by_variant_of`
removes two of the purge's three scans of `asset`. Slower, on purpose or tolerated: a claim
writes three more columns (owner, lease, retry time) and maintains one more index; the stats
count reads the retry time of queued jobs; `enqueue_once` among thousands of waiting jobs of
its *own* kind still reads each (no caller does that: the ML backfill reads the queue once).
A heartbeat thread per running job costs 0.08 ms to start and stop.

The table was measured before `asset_by_held_like` was added to the same migration: with it
the look-alike row no longer scans `asset` (asserted by query plan, not re-timed). Migration
`0025` added `album_by_cover` for the same `DELETE`'s check of `album.cover_asset_id` (asserted
by query plan, not timed) and `clip_embedding_by_asset` for its check of `clip_embedding`:
without planner statistics for that table the check scanned it, 46 ms per purged photo at 50k
embeddings, 0.06 ms with the index (measured with the ML work; here asserted by query plan).

## Commits without a disk flush each (`synchronous = NORMAL`)

400 single-statement commits (`INSERT INTO job`) on a library database file, ext4 on NVMe,
development machine, SQLite 3.45.1, two runs each:

| ms per commit | median | mean |
|---|---|---|
| WAL + `synchronous = FULL` (before) | 3.00 / 3.02 | 2.86 / 3.16 |
| WAL + `synchronous = NORMAL` (after) | **0.02 / 0.03** | 0.05 / 0.06 |

An imported photo is at least 5 commits, each under the one write lock, so about 15 ms of
waiting for the disk per photo is gone (2.5 min in 10k photos), and the other writers
(previews recording their paths, the job queue) no longer queue behind those flushes. Not
re-timed end to end. The trade-off and the three writes that still flush are in
`ARCHITECTURE.md` §3.

## Faces, people and look-alikes (ML and review)

Synthetic rows only, in a temp-file database on the development machine (16 cores, other work
running: single timings move by ±30 %): 25,000 photos, 50,000 faces of 512 numbers each
(60 people, 20,000 strangers that stay deferred), 25,000 CLIP vectors; an admin, a member and a
guest who see 25,000 / 16,667 / 8,333 photos through three sources. "Before" is `a1c0a0e`
(clustering: `5463926`).

**Nightly face clustering** (the global `cluster_faces {}` pass, also run at every start):

| | before | after |
|---|---|---|
| one deferred face: how many faces match, who is nearest | 184 + 226 ms (two scans) | 129–190 ms (one scan) |
| global pass, nothing added or placed since the last one | ≈ 137 min (20,000 × 410 ms, projected) | **0.24 s** |
| global pass after 100 new faces (strangers) | ≈ 138 min (projected) | **30 s** (200 steps + one comparison of the 100 with the 20,000) |
| first global pass after a server start | ≈ 137 min (projected) | ≈ 43–63 min (20,000 × one scan, projected); see "across a restart" below |

One statement now answers both questions with one distance per other face. The handler keeps
what the last global pass saw per face (person, state, creation time, start of the embedding;
about 0.15 s to read) and steps only the deferred faces within reach of a face that was added,
detected again or placed since — by clustering, or by a person on the People screen — in the
same id order, so the people are the ones a pass over every deferred face gives
(`tests/ml/test_ml_jobs.py`, random days against the old pass). Which deferred faces are near
N changed faces costs 20,000 × N distances in one statement: 0.08 s for 1, 2.9 s for 100, 20 s
for 500.

**The same pass across a restart** (migration 0026). That memory lived in the process, so the
first pass after every start stepped every deferred face once. It is now kept in the library:
`face_cluster_mark` holds each face as the last finished pass saw it, `face_cluster_pass` the
clustering settings of that pass. Measured on a second synthetic library of the same shape
(50,000 faces, 20,000 deferred; one scan took 99 ms that day, so "before" is 20,000 × 99 ms):

| first global pass after a server start | before | after |
|---|---|---|
| nothing added or placed since the last pass | ≈ 33 min (projected) | **0.09 s**, 0 rows written |
| 100 new faces (strangers) since the last pass | ≈ 33 min (projected) | **23 s** (200 steps 20 s, the 100 against the 20,000 2.1 s) |
| a library no pass has finished on (an upgrade, a changed reach or group size) | ≈ 33 min | the same, once; then as above |

A pass reads only the faces that differ from their mark (one statement, 0.07 s; 0.14 s when
nothing is kept yet) and at its end writes one row per face that differed plus one for the
pass, in one transaction: 101 rows in 0.02 s after 100 new faces, 1,001 rows in 0.008 s, 50,001
rows in 0.22 s for the first pass of a library (3.1 MB in the file, about 63 bytes a face).
Nothing changed: nothing written. A pass that fails or is cut off has written no mark, so the
next one sees everything it placed as a change and goes on from there; it steps every
deferred face only when `face_cluster_pass` has no row for the face model or one with other
settings. A mark goes with its face (foreign key), and holds the creation time and the start
of the embedding because a face id is used again (`tests/ml/test_ml_jobs.py`: the random days
now include restarts, passes cut off half way and a restart right after one).

**People and similar photos** (ms, median of 7; admin / member / guest):

| | before | after |
|---|---|---|
| `GET /people` (60 people) | 170 / 195 / 142 | 148 / 137 / 84 |
| `GET /people/{id}` (one of ~500 faces) | 59 / 67 / 50 | **2.6 / 3.9 / 3.2** |
| `GET /people/{id}/assets` (first 200) | 89 / 85 / 60 | **4.4 / 6.5 / 5.6** |
| rename (`PATCH /people/{id}`) | 93 / 82 / 61 | **7.4 / 7.1 / 6.5** |
| similar photos (`/assets/{id}/similar`) | 115 / 104 / 85 | 81 / 87 / 62 |

Measured at the use-case level (`People`, `SimilarPhotos`) without HTTP. Before, each request
listed every photo the viewer may see and copied the ids into a temp table; now the ML store
gets the viewer and puts the library's rule into its own statement: looked up for one person's
faces only, once per photo for whole-library reads (`/people`, similar photos). Those two still
check the rule for every photo with a face or a vector, which is what is left of their time
besides the 25,000 distances.

**Look-alikes held for review** (`domain.review.lookalikes`, pure Python, random hashes, a
tenth of the new photos within 4 bits of a library photo): 20,000 new photos against a
30,000-photo library took **58 s** (6 × 10⁸ comparisons; 1,000 timed, × 20) and now **0.38 s**:
library hashes are indexed by 5 bands of bits and a new photo meets only the hashes sharing a
band. Real hashes are less evenly spread than random ones, so expect more candidates per photo.

**Purging a photo with 50,000 embeddings stored**: the cascade into `clip_embedding` looks the
photo up by `asset_id`, but the table's only index starts with `model`. With planner statistics
for that table SQLite skips over the one model: 0.07 ms per delete. Without them (a library
whose `ANALYZE` ran before the first embedding existed) it reads the whole table, vectors
included: **46 ms** per delete. `CREATE INDEX clip_embedding_by_asset ON clip_embedding
(asset_id)` makes it 0.06 ms in both cases; not added here (it needs a migration).

## Import and previews (C28)

209 synthetic 12 MP JPEGs (4000 × 3000; synthetic files are ~200 KB, real ones ~4 MB, so real
hashing and copying cost more I/O; decoding costs the same), import + every preview until the
queue is idle:

| | ms / photo | 10k photos |
|---|---|---|
| before (one worker, WebP effort 4) | 409 | 68 min |
| after, measured on 2 cores (1 preview thread) | 215–226 | **36–38 min** |
| after, import lane alone | 97 | — |
| after, 4 cores (projection: 2 preview threads ≈ 110 ms/photo in parallel with the 97 ms import) | ≈ 110 | **≈ 19 min** (target 30) |

Per-step costs on these photos: thumbnail 640 px 70 ms; preview 2048 px 413 ms at WebP effort 4
→ **225 ms at effort 2**; preview + thumbnail from one decode 268 ms (vs 295 separately).
Imports (long lane) and previews (their own pool) now run in parallel, so decode-once is used
where both are rendered anyway: thumbnail repairs and edited renders (`render_edit`, queued
when a recipe is saved). The 4-core figure is a projection from the measured per-lane costs;
re-measure on the laptop with `scripts/perf/import_e2e.py`.

## Exposure settings (migration 0030)

2,144 synthetic photos (`make_mock_library.py --count 2000 --size 800`, 1,995 of them with
exposure tags), development machine (16 cores, other work running), median of 9 runs,
`uv run python scripts/perf/exposure_backfill.py <folder>`:

| | ms / photo | 10k photos |
|---|---|---|
| exposure backfill (read the library copy, store the four values; batches of 200) | **8.7** | 87 s |
| metadata read at import, without the four exposure tags | 7.94 | — |
| metadata read at import, with them | 8.37 | — |

The backfill is one ExifTool read per photo and one transaction per batch; it holds the
shared ExifTool process for one batch at a time (about 1.7 s), then lets an import in.
Importing reads the four tags in the ExifTool call it already makes: no second process, no
second pass. The read is 0.4 ms per photo slower (5 % of the read, under 0.5 % of the 97 ms
the import lane spends per photo), which is inside the run-to-run spread of the import
benchmark; not re-timed end to end.

## Home, the person filter and pinned photos (issue 54)

Synthetic rows only (no files), built by `uv run python scripts/perf/bench_home.py <photos>
<runs>`: 4 viewers, 6 sources with mixed access, ~15 years of bursts and trips, 70 % with a
place, 8 % with a guessed date, 2 % imported in the last week, faces of 20 people on 30 % of
the photos. Development machine with other work running (load average ~10 on 16 cores: the
timeline page, 4–5 ms in the table above, took 8–13 ms here), so read the calendar column, a
whole-library read timed in the same runs, as the yardstick. ms, admin / alice / bob / guest:

| | 10k photos (median of 15) | 50k photos (median of 9) |
|---|---|---|
| `GET /api/home` (all of it) | **57 / 76 / 61 / 57** | 271 / 366 / 353 / 287 |
| the same with trips away from home and months at home | 62 / 82 / 64 / 51 | 341 / 410 / 343 / 211 |
| of which: every visible photo's time and place | 45 / 61 / 44 / 40 | 203 / 302 / 231 / 204 |
| of which: the week's arrivals | 2.4 / 3.0 / 3.0 / 3.7 | 14 / 19 / 19 / 17 |
| calendar (same runs, for scale) | 17 / 33 / 38 / 35 | 96 / 183 / 163 / 145 |
| first 200 of `person_id=1&person_id=2` | 17 / 23 / 21 / 22 | 16 / 21 / 20 / 24 |
| first 200 of `pinned=true` | 0.1 / 0.1 / 0.1 / 0.0 | 0.3 / 0.3 / 0.3 / 0.0 |

Home reads every photo the viewer sees once (memories need all of their times); about half of
that is SQL (the visibility rule per photo, as for the calendar), half building one small
tuple per photo in Python. Only the eight trips shown are named and get a cover. At 10k it is
well inside the 200 ms budget, which is set for 10k photos (ARCHITECTURE §5; the v1 target
is under 10,000); at 50k it works in a third of a second, two to three times the calendar,
so it is not cached. Working out home and the months at home costs a few ms at 10k (the
second Home row, from a later and as loaded run). The person filter is an
`EXISTS` on `face_by_person` per photo and stops at the page's `LIMIT`; pinned starts from the
viewer's own marks, like favourites.

## Download estimates (A14)

Estimates now start from each photo's real bytes: `bytes × as-JPEG factor (per source type) ×
format factor (jpeg 0.95, webp 0.4, png 3.7) × quality curve × (pixel ratio ^ 0.55/0.5/0.8)`.
Calibrated with the real renderer on 48 synthetic photos (800–4000 px, q90); WebP and PNG
factors sit between the synthetic results (0.24, 2.7) and typical camera photos (~0.65, ~5) so
both stay within 2×. Median estimate / actual on the calibration set:

| format | full size | 2048 | 1024 | 200 |
|---|---|---|---|---|
| jpeg | 0.97 | 0.97 | 0.97 | 0.75 |
| webp | 1.27 | 1.27 | 1.27 | 1.13 |
| png | 1.11 | 1.11 | 1.11 | 1.02 |

Before, the bytes-per-pixel guesses were 10–30× too high on the synthetic E2E library.
