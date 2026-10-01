-- 0011: one non-destructive edit recipe per photo (FEATURES 4c). The version only grows, so
-- image URLs (?v=) change on every edit and revert.
CREATE TABLE edit_recipe (
    asset_id     INTEGER PRIMARY KEY REFERENCES asset(id),
    recipe_json  TEXT    NOT NULL,
    updated_by   INTEGER REFERENCES user(id),
    updated_at   TEXT    NOT NULL
);
ALTER TABLE asset ADD COLUMN edit_version INTEGER NOT NULL DEFAULT 0;
