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
