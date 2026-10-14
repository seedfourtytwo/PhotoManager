-- 0031: Keep on my phone (FEATURES 10.6; approved by C 2026-10-14).
--
-- sync_rule: what one device keeps (include) or leaves off (exclude): an album, a person, or
-- the timeline's filters as JSON (the shape of /api/assets' query, search facets in "q").
-- A thing is named once per device; its mode can change. An album or person that goes takes
-- its rules with it.
CREATE TABLE sync_rule (
    id           INTEGER PRIMARY KEY,
    device_id    INTEGER NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    kind         TEXT    NOT NULL CHECK (kind IN ('album', 'person', 'filter')),
    album_id     INTEGER REFERENCES album(id) ON DELETE CASCADE,
    person_id    INTEGER REFERENCES person(id) ON DELETE CASCADE,
    filter_json  TEXT,
    mode         TEXT    NOT NULL CHECK (mode IN ('include', 'exclude')),
    created_at   TEXT    NOT NULL,
    CHECK ((kind = 'album') = (album_id IS NOT NULL)
       AND (kind = 'person') = (person_id IS NOT NULL)
       AND (kind = 'filter') = (filter_json IS NOT NULL))
);
CREATE UNIQUE INDEX sync_rule_once
    ON sync_rule (device_id, kind, COALESCE(album_id, person_id, filter_json));
CREATE INDEX sync_rule_by_album ON sync_rule (album_id) WHERE album_id IS NOT NULL;
CREATE INDEX sync_rule_by_person ON sync_rule (person_id) WHERE person_id IS NOT NULL;

-- sync_sent: the photos the phone said it saved (POST /api/sync/sent; downloading marks
-- nothing), so "only new" leaves them out. Deletions on the phone never come back: a photo
-- deleted there stays sent (one way).
-- device.sync_cursor (0014) stays unused: a cursor cannot tell that an old photo joined an album.
CREATE TABLE sync_sent (
    device_id  INTEGER NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    asset_id   INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    sent_at    TEXT    NOT NULL,
    PRIMARY KEY (device_id, asset_id)
) WITHOUT ROWID;
CREATE INDEX sync_sent_by_asset ON sync_sent (asset_id);
