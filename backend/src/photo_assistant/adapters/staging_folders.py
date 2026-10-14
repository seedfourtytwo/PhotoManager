"""The app's own pulled copies of cloud sources: ``data/staging/<source id>``."""

import shutil
from pathlib import Path


class StagingFolders:
    def __init__(self, root: Path) -> None:
        self._root = root

    def remove(self, source_id: int) -> None:
        """Delete one source's copy. A link in its place is removed, never followed: what
        it points at is not the app's to delete."""
        folder = self._root / str(source_id)
        if folder.is_symlink():
            folder.unlink()
        elif folder.is_dir():
            shutil.rmtree(folder)
