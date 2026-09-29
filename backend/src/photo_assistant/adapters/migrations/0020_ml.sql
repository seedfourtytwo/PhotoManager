-- 0020: local ML (M3) — CLIP embeddings, faces, people, auto-tags, per-task status.
--
-- Vectors are float32 little-endian BLOBs: sqlite-vec's native layout, so its SQL functions
-- (vec_distance_cosine) read them directly. They live in ordinary tables rather than vec0
-- virtual tables because (a) the migration runner cannot load extensions, and (b) vec0 fixes
-- the dimension per table while the CLIP model (512/640/768/1024-d) is a setting. Brute-force
-- KNN over ≤100k rows is well inside the 500 ms search budget.

CREATE TABLE ml_task (
    asset_id    INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    task        TEXT    NOT NULL,          -- embed_clip | detect_faces | auto_tag
    model       TEXT    NOT NULL,
    status      TEXT    NOT NULL,          -- done | model_missing | failed
    detail      TEXT,
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (asset_id, task, model)
);
CREATE INDEX ml_task_by_status ON ml_task (task, model, status);

CREATE TABLE clip_embedding (
    model      TEXT    NOT NULL,
    asset_id   INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    dim        INTEGER NOT NULL,
    embedding  BLOB    NOT NULL CHECK (length(embedding) = 4 * dim),
    PRIMARY KEY (model, asset_id)
);

CREATE TABLE person (
    id             INTEGER PRIMARY KEY,
    name           TEXT,
    cover_face_id  INTEGER REFERENCES face(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE face (
    id              INTEGER PRIMARY KEY,
    asset_id        INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    model           TEXT    NOT NULL,
    box_x           REAL    NOT NULL,       -- fractions of the displayed image
    box_y           REAL    NOT NULL,
    box_w           REAL    NOT NULL,
    box_h           REAL    NOT NULL,
    score           REAL    NOT NULL,
    landmarks_json  TEXT    NOT NULL,
    dim             INTEGER NOT NULL,
    embedding       BLOB    NOT NULL CHECK (length(embedding) = 4 * dim),
    person_id       INTEGER REFERENCES person(id) ON DELETE SET NULL,
    assigned_by     TEXT,                   -- model | user (user choices are never undone)
    cluster_state   TEXT    NOT NULL DEFAULT 'new',  -- new | deferred | done
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX face_by_asset ON face (asset_id);
CREATE INDEX face_by_person ON face (person_id);
CREATE INDEX face_cluster_queue ON face (model, cluster_state, id);

CREATE TABLE tag (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    kind  TEXT NOT NULL DEFAULT 'auto'      -- auto | manual
);

CREATE TABLE asset_tag (
    asset_id  INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    score     REAL,
    by        TEXT NOT NULL,                -- model | user
    model     TEXT,
    PRIMARY KEY (asset_id, tag_id)
);
CREATE INDEX asset_tag_by_tag ON asset_tag (tag_id);

CREATE TABLE asset_ml_flag (
    asset_id            INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
    screen_or_document  INTEGER NOT NULL,   -- hides screenshots/documents from memories
    model               TEXT    NOT NULL
);
