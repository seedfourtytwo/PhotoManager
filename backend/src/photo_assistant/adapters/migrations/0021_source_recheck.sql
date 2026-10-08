-- 0021: a source can check itself again on a timer (issues 7 and 8). 'off' = only when asked,
-- which is what every source that already exists keeps doing.
ALTER TABLE source ADD COLUMN recheck TEXT NOT NULL DEFAULT 'off'
    CHECK (recheck IN ('off', 'hourly', 'daily', 'weekly'));
