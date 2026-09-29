-- 0008: places from offline reverse geocoding (FEATURES 2.4). One row per distinct place.
CREATE TABLE place (
    id       INTEGER PRIMARY KEY,
    country  TEXT NOT NULL,
    region   TEXT NOT NULL DEFAULT '',
    city     TEXT NOT NULL DEFAULT '',
    UNIQUE (country, region, city)
);
ALTER TABLE asset ADD COLUMN place_id INTEGER REFERENCES place(id);
CREATE INDEX asset_by_place ON asset (place_id);
