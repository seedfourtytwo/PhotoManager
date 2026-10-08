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

## Job queue and purge indexes (migration 0021)

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
the look-alike row no longer scans `asset` (asserted by query plan, not re-timed). Not fixed
here: the same `DELETE` checks `clip_embedding` and `album.cover_asset_id` without a usable index
(not measured: the synthetic library has no embeddings).

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
