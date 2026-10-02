-- 0017: QA fixes after M2 (fix/backend). One migration for the whole fix branch.

-- Private is marked by a person, not owned by "whoever imported the photo first" (QA A3).
-- A private photo is hidden from everyone who reaches it only through sources the marker
-- owns (and through albums); the marker, and anyone who reaches it through a source the
-- marker does not own, still see it. Existing private photos keep their old meaning: they
-- were private to the owner of their first source.
ALTER TABLE asset ADD COLUMN private_by INTEGER REFERENCES user(id);
UPDATE asset SET private_by = COALESCE(
        (SELECT s.owner_id FROM source s WHERE s.id = asset.first_source_id),
        (SELECT MIN(id) FROM user WHERE role = 'admin'))
 WHERE private = 1;

-- Crops smaller than 1/1000 of the photo are no longer valid (QA A6: they broke renders and
-- ZIPs). Drop such recipes (the photo shows unedited) and bump the version so caches refresh.
UPDATE asset SET edit_version = edit_version + 1
 WHERE id IN (SELECT asset_id FROM edit_recipe
               WHERE json_extract(recipe_json, '$.crop.w') < 0.001
                  OR json_extract(recipe_json, '$.crop.h') < 0.001);
DELETE FROM edit_recipe
 WHERE json_extract(recipe_json, '$.crop.w') < 0.001
    OR json_extract(recipe_json, '$.crop.h') < 0.001;

-- Capture times are wall-clock to the second everywhere (QA A12): mtime-based dates were
-- stored with microseconds.
UPDATE asset SET taken_at = substr(taken_at, 1, 19) WHERE length(taken_at) > 19;

-- Foreign keys the M2 integrations left out (B19). SQLite can't add them to a table, so the
-- tables are rebuilt; rows pointing at nothing (none expected) are dropped on the way.
CREATE TABLE inbox_new (
    user_id    INTEGER PRIMARY KEY REFERENCES user(id) ON DELETE CASCADE,
    source_id  INTEGER NOT NULL UNIQUE REFERENCES source(id)
);
INSERT INTO inbox_new (user_id, source_id)
    SELECT user_id, source_id FROM inbox
     WHERE user_id IN (SELECT id FROM user) AND source_id IN (SELECT id FROM source);
DROP TABLE inbox;
ALTER TABLE inbox_new RENAME TO inbox;

CREATE TABLE device_new (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    platform      TEXT    NOT NULL DEFAULT 'other',
    token_hash    TEXT    NOT NULL UNIQUE,
    created_at    TEXT    NOT NULL,
    last_used_at  TEXT,
    revoked_at    TEXT,
    last_sync_at  TEXT,
    sync_cursor   TEXT
);
INSERT INTO device_new SELECT * FROM device WHERE user_id IN (SELECT id FROM user);
DROP TABLE device;
ALTER TABLE device_new RENAME TO device;
CREATE INDEX device_by_user ON device (user_id, id);

CREATE TABLE backup_run_new (
    id             INTEGER PRIMARY KEY,
    target_id      INTEGER NOT NULL REFERENCES backup_target(id) ON DELETE CASCADE,
    kind           TEXT    NOT NULL DEFAULT 'backup',
    status         TEXT    NOT NULL,
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
INSERT INTO backup_run_new SELECT * FROM backup_run
 WHERE target_id IN (SELECT id FROM backup_target);
DROP TABLE backup_run;
ALTER TABLE backup_run_new RENAME TO backup_run;
CREATE INDEX backup_run_by_target ON backup_run (target_id, kind, id DESC);

-- The timeline reads live photos newest first (C25): a partial index walks them in order.
CREATE INDEX asset_live_timeline ON asset (taken_at DESC, id DESC) WHERE trashed_at IS NULL;
