-- Indexes for what deleting a photo looks up. Additive only.

-- A purge clears the cover of the albums a photo fronts, and the foreign key on
-- cover_asset_id is checked on every DELETE FROM asset: both scanned the whole album table.
CREATE INDEX album_by_cover ON album (cover_asset_id) WHERE cover_asset_id IS NOT NULL;
