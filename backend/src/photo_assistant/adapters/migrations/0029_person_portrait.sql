-- 0029: a person's portrait can be chosen (issue 53; asked for by C 2026-10-13).
--
-- The round picture is a circle on the photo of the cover face: its centre as fractions of
-- the photo as displayed (without edits), and its size as a fraction of the shorter edge.
-- All three empty = the automatic circle round the face, as for everyone found before this.
ALTER TABLE person ADD COLUMN portrait_cx REAL;
ALTER TABLE person ADD COLUMN portrait_cy REAL;
ALTER TABLE person ADD COLUMN portrait_size REAL;
