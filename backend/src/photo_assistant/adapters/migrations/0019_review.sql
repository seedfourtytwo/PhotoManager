-- 0019: photos held for review (issue 8). A doubtful photo is imported like any other, then
-- kept out of the library until a person keeps or discards it.
ALTER TABLE asset ADD COLUMN held_reason TEXT;   -- NULL = in the library; 'lookalike' or a clutter tag
ALTER TABLE asset ADD COLUMN held_like INTEGER;  -- a look-alike: the library photo it resembles
ALTER TABLE asset ADD COLUMN reviewed_at TEXT;   -- a person decided about it: never held again
CREATE INDEX asset_by_held ON asset (held_reason) WHERE held_reason IS NOT NULL;
