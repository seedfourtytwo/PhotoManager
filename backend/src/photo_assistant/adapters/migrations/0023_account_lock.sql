-- 0023: wrong PINs are counted per account, and too many lock it (owner decision, security).
--
-- The 15-minute limit still reads login_failure, but those rows are pruned daily, so the
-- running count since the last good sign-in lives on the account. At 30 the account is locked
-- (locked_at is set) until an admin unlocks it or it is given a new PIN; a restart or the
-- pruning never lifts it. Existing accounts start with no wrong PINs and unlocked.
ALTER TABLE user ADD COLUMN failed_pins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user ADD COLUMN locked_at TEXT;
