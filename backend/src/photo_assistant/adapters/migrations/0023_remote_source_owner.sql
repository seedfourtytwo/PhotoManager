-- 0023: every source has an owner (owner decision, 2026-10).
--
-- Sources added from a cloud remote (rclone, Proton Drive) were created without an owner.
-- "Private" hides a photo from people who reach it only through sources its marker owns, so
-- on an ownerless source the mark hid the photo from nobody. New cloud sources now belong to
-- the admin who adds them, like folder sources; the ownerless ones already here go to the
-- first admin (the same choice 0017 made for private photos without an owner), counting only
-- admins who can still log in.
--
-- A library that has no admin yet keeps its sources ownerless: the first-run setup hands
-- them to the first admin (add_first_admin), as it does for an M1 library.
-- Access lists are not touched: who may see a source is a separate decision.
UPDATE source
   SET owner_id = (SELECT MIN(id) FROM user WHERE role = 'admin' AND disabled = 0)
 WHERE owner_id IS NULL;
