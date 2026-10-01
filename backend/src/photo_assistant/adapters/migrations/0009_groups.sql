-- 0009: perceptual hash and burst / near-duplicate groups (FEATURES 2.5).
ALTER TABLE asset ADD COLUMN phash TEXT;       -- 64-bit pHash of the thumbnail, hex
ALTER TABLE asset ADD COLUMN group_id INTEGER; -- smallest asset id of the group; NULL = alone
CREATE INDEX asset_by_group ON asset (group_id);
