-- 0032: an account pins photos to its Home (issue 54), like a favourite: its own, per photo.
--
-- NULL = not pinned; else when it was pinned (UTC), kept when the photo is pinned again.
ALTER TABLE user_asset ADD COLUMN pinned_at TEXT;
