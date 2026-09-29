-- 0002: remember size + mtime of each source file so rescans can skip unchanged files.
ALTER TABLE asset_source ADD COLUMN byte_size INTEGER;
ALTER TABLE asset_source ADD COLUMN mtime_ns INTEGER;
