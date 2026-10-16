-- 0034: each photo's dominant colour, the placeholder a grid paints until the thumbnail
-- arrives (Flight UI rebuild plan, backend change 15; approved by C 2026-10-15).
--
-- "#rrggbb", read from the thumbnail by the colour job (app/enrich.py, rule in
-- domain/colour.py); NULL until then. The job runs after every import and once at start-up,
-- so photos imported before this get theirs without anyone asking. The partial index keeps
-- finding the photos still without one cheap however large the library grows.
ALTER TABLE asset ADD COLUMN colour TEXT;
CREATE INDEX asset_without_colour ON asset (id) WHERE colour IS NULL AND thumb_path IS NOT NULL;
