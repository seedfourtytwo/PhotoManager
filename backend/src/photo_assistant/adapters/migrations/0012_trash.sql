-- 0012: soft delete with a 30-day trash (FEATURES 11.3). Purged content is remembered by hash
-- so a rescan of a source that still has the file does not bring it back.
ALTER TABLE asset ADD COLUMN trashed_at TEXT;
ALTER TABLE asset ADD COLUMN trashed_by INTEGER REFERENCES user(id);
CREATE INDEX asset_by_trashed ON asset (trashed_at);

CREATE TABLE purged_hash (
    content_hash  TEXT PRIMARY KEY,
    purged_at     TEXT NOT NULL
);
