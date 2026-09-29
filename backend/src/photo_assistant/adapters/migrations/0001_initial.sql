-- 0001: library core (M1). Every path column is relative to the data root.

CREATE TABLE source (
    id          INTEGER PRIMARY KEY,
    kind        TEXT    NOT NULL DEFAULT 'folder',
    label       TEXT    NOT NULL,
    root        TEXT    NOT NULL UNIQUE,   -- external, machine-specific by nature
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE asset (
    id               INTEGER PRIMARY KEY,
    content_hash     TEXT    NOT NULL UNIQUE,
    kind             TEXT    NOT NULL,
    mime_type        TEXT,
    byte_size        INTEGER NOT NULL,
    width            INTEGER,             -- as displayed (orientation applied)
    height           INTEGER,
    taken_at         TEXT    NOT NULL,    -- local wall-clock, ISO 8601, no zone
    tz_offset_min    INTEGER,
    date_source      TEXT    NOT NULL,
    latitude         REAL,
    longitude        REAL,
    camera_make      TEXT,
    camera_model     TEXT,
    orientation      INTEGER,
    library_path     TEXT    NOT NULL,
    thumb_path       TEXT,
    thumb_w          INTEGER,
    thumb_h          INTEGER,
    preview_path     TEXT,
    variant_of       INTEGER REFERENCES asset(id),
    imported_at      TEXT    NOT NULL
);
CREATE INDEX asset_timeline ON asset (taken_at DESC, id DESC);

CREATE TABLE asset_source (
    asset_id       INTEGER NOT NULL REFERENCES asset(id),
    source_id      INTEGER NOT NULL REFERENCES source(id),
    relative_path  TEXT    NOT NULL,
    seen_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (source_id, relative_path)
);
CREATE INDEX asset_source_by_asset ON asset_source (asset_id);

CREATE TABLE import_run (
    id           INTEGER PRIMARY KEY,
    source_id    INTEGER NOT NULL REFERENCES source(id),
    status       TEXT    NOT NULL,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT    NOT NULL,
    ignored      INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT    NOT NULL,
    message      TEXT
);

CREATE TABLE import_item (
    run_id         INTEGER NOT NULL REFERENCES import_run(id),
    relative_path  TEXT    NOT NULL,
    outcome        TEXT    NOT NULL,
    reason         TEXT,
    asset_id       INTEGER
);
CREATE INDEX import_item_by_run ON import_item (run_id, outcome);

CREATE TABLE job (
    id           INTEGER PRIMARY KEY,
    kind         TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'queued',  -- queued | running | done | failed
    attempts     INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX job_queue ON job (status, id);
