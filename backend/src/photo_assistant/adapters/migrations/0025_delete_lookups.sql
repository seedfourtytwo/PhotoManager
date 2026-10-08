-- Indexes for what deleting a photo looks up. Additive only.

-- A purge clears the cover of the albums a photo fronts, and the foreign key on
-- cover_asset_id is checked on every DELETE FROM asset: both scanned the whole album table.
CREATE INDEX album_by_cover ON album (cover_asset_id) WHERE cover_asset_id IS NOT NULL;

-- The same DELETE checks clip_embedding, whose primary key starts with the model: without
-- planner statistics for the table (a library analysed before its first embedding existed)
-- that check scanned it, vectors and all (46 ms per purged photo at 50k embeddings).
CREATE INDEX clip_embedding_by_asset ON clip_embedding (asset_id);
