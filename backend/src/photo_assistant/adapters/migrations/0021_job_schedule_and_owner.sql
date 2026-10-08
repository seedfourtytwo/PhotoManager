-- Jobs: a retry waits its turn, and a running job belongs to the process that claimed it.
-- Additive only: rows from before keep NULL everywhere (run at once; no lease, so a job that
-- was 'running' counts as cut off and is queued again by the next server start).

ALTER TABLE job ADD COLUMN run_after  TEXT;  -- not before this instant (UTC ISO); NULL = now
ALTER TABLE job ADD COLUMN claimed_by TEXT;  -- owner id of the claiming process, e.g. server-…
ALTER TABLE job ADD COLUMN claimed_at TEXT;  -- claim time, renewed while the job runs

-- Only the waiting jobs, by kind: a lane's poll and enqueue_once seek straight to their own
-- kinds instead of walking every queued job of the other lanes (10k previews after an import).
CREATE INDEX job_waiting ON job (kind, id) WHERE status = 'queued';

-- Purging a photo clears the variants pointing at it, and the foreign key on variant_of is
-- checked on every DELETE FROM asset: both scanned the whole table.
CREATE INDEX asset_by_variant_of ON asset (variant_of) WHERE variant_of IS NOT NULL;
