-- 0003: add the inode change time to source fingerprints. Unlike mtime, it cannot be set back
-- by tools like `cp -p` or `rsync -t`, so a replaced file is always noticed.
ALTER TABLE asset_source ADD COLUMN ctime_ns INTEGER;
