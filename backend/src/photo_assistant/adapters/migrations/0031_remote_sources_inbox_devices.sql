-- 0031 (integrator: renumber after the core branch's migrations).
-- Remote (rclone) sources keep {"remote", "path"} here; credentials stay in rclone's config.
ALTER TABLE source ADD COLUMN config_json TEXT;

-- One upload inbox source per user (data/inbox/<user_id>/). user_id refers to user(id) once
-- the accounts table exists (not declared as a foreign key so this migration stands alone).
CREATE TABLE inbox (
    user_id    INTEGER PRIMARY KEY,
    source_id  INTEGER NOT NULL UNIQUE REFERENCES source(id)
);

-- Non-browser clients (Apple Shortcuts, later the phone app). Only a hash of the token is kept.
CREATE TABLE device (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    name          TEXT    NOT NULL,
    platform      TEXT    NOT NULL DEFAULT 'other',
    token_hash    TEXT    NOT NULL UNIQUE,
    created_at    TEXT    NOT NULL,
    last_used_at  TEXT,
    revoked_at    TEXT,
    last_sync_at  TEXT,   -- ARCHITECTURE §3, for server → phone sync later
    sync_cursor   TEXT
);
CREATE INDEX device_by_user ON device (user_id, id);
