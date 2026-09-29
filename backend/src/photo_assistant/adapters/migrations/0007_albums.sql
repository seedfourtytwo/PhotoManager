-- 0007: albums with an owner, members (viewer/editor) and ordered items (FEATURES 5.1, 5.2, 8.4).
CREATE TABLE album (
    id              INTEGER PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES user(id),
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    cover_asset_id  INTEGER REFERENCES asset(id),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX album_by_owner ON album (owner_id);

CREATE TABLE album_member (
    album_id  INTEGER NOT NULL REFERENCES album(id),
    user_id   INTEGER NOT NULL REFERENCES user(id),
    role      TEXT    NOT NULL CHECK (role IN ('viewer', 'editor')),
    PRIMARY KEY (album_id, user_id)
);
CREATE INDEX album_member_by_user ON album_member (user_id);

CREATE TABLE album_item (
    album_id  INTEGER NOT NULL REFERENCES album(id),
    asset_id  INTEGER NOT NULL REFERENCES asset(id),
    position  INTEGER NOT NULL,
    PRIMARY KEY (album_id, asset_id)
);
CREATE INDEX album_item_by_asset ON album_item (asset_id);
