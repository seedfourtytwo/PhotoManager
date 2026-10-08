-- What the last finished global face-clustering pass saw, kept in the library so the first
-- pass after a server start goes on from it instead of stepping every waiting face again
-- (app/ml_jobs.py, ClusterFaces). Additive: no existing table changes.

-- One row per face model once a global pass has finished, with the clustering settings it
-- ran with. No row, or other settings than today's: the next pass steps every waiting face.
-- A later change to the clustering rule itself only has to empty this table.
CREATE TABLE face_cluster_pass (
    model  TEXT PRIMARY KEY,
    rule   TEXT NOT NULL
);

-- The face as that pass saw it. A face whose row here differs from the face (or has none)
-- was added, detected again, placed or moved on since. Written at the end of a pass in one
-- transaction with face_cluster_pass; the rows go with their face (and so with its photo).
CREATE TABLE face_cluster_mark (
    face_id        INTEGER PRIMARY KEY REFERENCES face(id) ON DELETE CASCADE,
    person_id      INTEGER,            -- only compared, so not a reference
    cluster_state  TEXT NOT NULL,
    created_at     TEXT NOT NULL,      -- with the fingerprint: a face id is used again
    fingerprint    BLOB NOT NULL       -- the first 16 bytes of the embedding
);
