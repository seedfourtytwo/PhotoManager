-- 0016: backup targets and their runs (FEATURES 9b).
-- repository and password_file are machine-specific by nature (like source.root): they point
-- outside the portable data root. The password itself is never stored here.

CREATE TABLE backup_target (
    id             INTEGER PRIMARY KEY,
    label          TEXT    NOT NULL UNIQUE,
    kind           TEXT    NOT NULL CHECK (kind IN ('local', 'rclone')),
    repository     TEXT    NOT NULL,          -- /media/c/Backup/photos or rclone:server:photos
    password_file  TEXT    NOT NULL,          -- absolute path, outside the library
    schedule       TEXT    NOT NULL DEFAULT 'daily 02:30',
    quiet_window   TEXT,                      -- '22:00-06:00' or NULL for any time
    retention_json TEXT    NOT NULL,          -- {"daily": 7, "weekly": 4, "monthly": 12}
    enabled        INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT    NOT NULL
);

CREATE TABLE backup_run (
    id             INTEGER PRIMARY KEY,
    target_id      INTEGER NOT NULL REFERENCES backup_target(id),
    kind           TEXT    NOT NULL DEFAULT 'backup',  -- backup | check | restore_test
    status         TEXT    NOT NULL,                   -- running | succeeded | failed
    started_at     TEXT    NOT NULL,
    finished_at    TEXT,
    snapshot_id    TEXT,
    bytes_added    INTEGER,
    files_new      INTEGER,
    files_changed  INTEGER,
    repo_bytes     INTEGER,
    error          TEXT,
    details        TEXT
);
CREATE INDEX backup_run_by_target ON backup_run (target_id, kind, id DESC);
