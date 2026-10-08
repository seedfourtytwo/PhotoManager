-- 0020: an off-site copy of a local backup on Proton Drive (issue 14). NULL = no copy;
-- otherwise the folder in "My files" that holds it. Each copy run is a backup_run of kind
-- 'mirror'.
ALTER TABLE backup_target ADD COLUMN mirror_path TEXT;
