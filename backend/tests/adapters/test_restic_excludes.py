"""What a crash left half-written (``*.partial``) is not backed up: it is not a photo, and a
half-written database snapshot restored as if it were whole would be worse than none."""

import shutil
from pathlib import Path

import pytest

from photo_assistant.adapters.restic_backup import ResticBackup
from photo_assistant.domain.backup import BACKUP_FOLDERS
from photo_assistant.ports.backup import RepositoryRef

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing"),
]


def test_crash_leftovers_are_not_in_the_snapshot(tmp_path: Path) -> None:
    library = tmp_path / "data"
    photo = library / "originals" / "2020" / "01" / f"{1:064x}.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"a whole photo")
    (photo.parent / "3f2a.partial").write_bytes(b"half a pho")
    (library / "db-snapshot").mkdir()
    (library / "db-snapshot" / "library.db").write_bytes(b"a whole snapshot")
    (library / "db-snapshot" / "library.db.partial").write_bytes(b"half a snap")
    password = tmp_path / "secrets" / "restic-password"
    password.parent.mkdir()
    password.write_text("correct horse battery staple\n")
    repo = RepositoryRef(str(tmp_path / "backup-disk" / "photos"), password)
    engine = ResticBackup(cache_dir=tmp_path / "restic-cache")
    Path(repo.location).parent.mkdir(parents=True)
    engine.ensure_repository(repo)

    snapshot = engine.backup(repo, library, BACKUP_FOLDERS)

    restored = tmp_path / "restored"
    engine.restore(repo, snapshot.snapshot_id, list(BACKUP_FOLDERS), restored)
    files = sorted(p.relative_to(restored).as_posix() for p in restored.rglob("*") if p.is_file())
    assert files == ["db-snapshot/library.db", f"originals/2020/01/{1:064x}.jpg"]
    assert snapshot.files_new == 2
    assert (photo.parent / "3f2a.partial").exists(), "the backup deletes nothing in the library"
