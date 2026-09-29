-- 0010: manual date fixes keep the previous value (FEATURES 2.12).
CREATE TABLE date_change (
    id                 INTEGER PRIMARY KEY,
    asset_id           INTEGER NOT NULL REFERENCES asset(id),
    old_taken_at       TEXT    NOT NULL,
    old_tz_offset_min  INTEGER,
    old_date_source    TEXT    NOT NULL,
    new_taken_at       TEXT    NOT NULL,
    changed_by         INTEGER REFERENCES user(id),
    changed_at         TEXT    NOT NULL
);
CREATE INDEX date_change_by_asset ON date_change (asset_id);
