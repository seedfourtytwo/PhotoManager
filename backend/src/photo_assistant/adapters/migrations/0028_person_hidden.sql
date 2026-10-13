-- 0028: a person can be hidden from People (issue 53; asked for by C 2026-10-13).
--
-- For a stranger in the background of a few photos. The person and their faces stay, so a
-- later photo of the same stranger joins them instead of coming back as a new "Someone";
-- they are only left out of the lists. 0 = listed, as everyone found before this was.
ALTER TABLE person ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1));
