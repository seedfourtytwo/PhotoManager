-- 0017: QA fixes after M2 (fix/backend). One migration for the whole fix branch.

-- Private is marked by a person, not owned by "whoever imported the photo first" (QA A3).
-- A private photo is hidden from everyone who reaches it only through sources the marker
-- owns (and through albums); the marker, and anyone who reaches it through a source the
-- marker does not own, still see it. Existing private photos keep their old meaning: they
-- were private to the owner of their first source.
ALTER TABLE asset ADD COLUMN private_by INTEGER REFERENCES user(id);
UPDATE asset SET private_by = COALESCE(
        (SELECT s.owner_id FROM source s WHERE s.id = asset.first_source_id),
        (SELECT MIN(id) FROM user WHERE role = 'admin'))
 WHERE private = 1;

-- Crops smaller than 1/1000 of the photo are no longer valid (QA A6: they broke renders and
-- ZIPs). Drop such recipes (the photo shows unedited) and bump the version so caches refresh.
UPDATE asset SET edit_version = edit_version + 1
 WHERE id IN (SELECT asset_id FROM edit_recipe
               WHERE json_extract(recipe_json, '$.crop.w') < 0.001
                  OR json_extract(recipe_json, '$.crop.h') < 0.001);
DELETE FROM edit_recipe
 WHERE json_extract(recipe_json, '$.crop.w') < 0.001
    OR json_extract(recipe_json, '$.crop.h') < 0.001;

-- Capture times are wall-clock to the second everywhere (QA A12): mtime-based dates were
-- stored with microseconds.
UPDATE asset SET taken_at = substr(taken_at, 1, 19) WHERE length(taken_at) > 19;
