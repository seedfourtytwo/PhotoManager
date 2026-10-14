-- 0030: how a photo was exposed (redesign spec §4.3; approved by C 2026-10-13).
--
-- Aperture (f-number), shutter time (seconds), ISO and focal length (millimetres), each on
-- its own and nullable: a scan has none, an old camera may have left one out. What a value
-- may be is decided in domain/exposure.py, not here. Photos imported before this have none
-- until `just exposure-backfill` reads them from the library copy (read-only).
ALTER TABLE asset ADD COLUMN f_number REAL;
ALTER TABLE asset ADD COLUMN exposure_time REAL;
ALTER TABLE asset ADD COLUMN iso INTEGER;
ALTER TABLE asset ADD COLUMN focal_length REAL;
