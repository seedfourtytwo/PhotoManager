-- 0005: who may see what. A source has an owner and an access list; an asset may be marked
-- private by its owner.

ALTER TABLE source ADD COLUMN owner_id INTEGER REFERENCES user(id);

CREATE TABLE source_access (
    source_id  INTEGER NOT NULL REFERENCES source(id),
    user_id    INTEGER REFERENCES user(id),               -- NULL = everyone
    level      INTEGER NOT NULL CHECK (level BETWEEN 1 AND 3)  -- 1 view, 2 download, 3 edit
);
CREATE UNIQUE INDEX source_access_one ON source_access (source_id, IFNULL(user_id, 0));
CREATE INDEX source_access_by_user ON source_access (user_id);

-- Sources from M1 keep working for everyone, like new ones (contract default: download).
INSERT INTO source_access (source_id, user_id, level) SELECT id, NULL, 2 FROM source;

-- The owner of an asset is the owner of the source it was first imported from.
ALTER TABLE asset ADD COLUMN first_source_id INTEGER REFERENCES source(id);
ALTER TABLE asset ADD COLUMN private INTEGER NOT NULL DEFAULT 0;
UPDATE asset SET first_source_id = (
    SELECT x.source_id FROM asset_source x WHERE x.asset_id = asset.id ORDER BY x.rowid LIMIT 1
);
