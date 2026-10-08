-- 0018: guided backup setup (issue 3). The app now makes the encryption key itself, so it
-- must know whether the owner confirmed keeping a copy outside this machine. Targets from
-- before use a password file their owner wrote: they count as saved.

ALTER TABLE backup_target ADD COLUMN key_saved_at TEXT;
UPDATE backup_target SET key_saved_at = created_at;
