-- 0006: per-user state on a photo (FEATURES 3.3, 8.5). Private is per asset (set by its owner).
CREATE TABLE user_asset (
    user_id    INTEGER NOT NULL REFERENCES user(id),
    asset_id   INTEGER NOT NULL REFERENCES asset(id),
    favourite  INTEGER NOT NULL DEFAULT 0,
    hidden     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, asset_id)
);
CREATE INDEX user_asset_by_asset ON user_asset (asset_id);
