-- 0027: each account has its own look (issue 11, docs/adr/0001; approved by C 2026-10-08).
--
-- One sheet of named values as JSON text: a theme, a mode, a few dials and switches. Never
-- CSS. NULL means "the defaults", so existing accounts look as they did. What a sheet may
-- hold is decided in domain/look.py, not here: a sheet that no longer passes reads as the
-- defaults.
ALTER TABLE user ADD COLUMN look TEXT;
