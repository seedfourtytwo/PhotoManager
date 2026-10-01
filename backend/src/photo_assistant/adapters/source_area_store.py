"""A LibraryStore that lets folders *inside* the data root's source areas be sources.

The importer refuses any source that overlaps the library (so nobody imports the library into
itself). Remote pulls (``data/staging/<id>``) and phone uploads (``data/inbox/<user>``) live
inside the data root on purpose — they move with it — so they need this narrow exception:
only folders strictly inside an area are allowed; the areas themselves, the data root and
everything else in it are still refused.
"""

from collections.abc import Iterable
from contextlib import AbstractContextManager
from pathlib import Path

from photo_assistant.ports import LibraryStore


class SourceAreaStore:
    def __init__(self, inner: LibraryStore, areas: Iterable[Path]) -> None:
        self._inner = inner
        self._areas = [a.resolve() for a in areas]

    def overlaps(self, folder: Path) -> bool:
        resolved = folder.resolve()
        if any(area in resolved.parents for area in self._areas):
            return False
        return self._inner.overlaps(folder)

    def store_original(self, source_file: Path, relative_path: str, content_hash: str) -> None:
        self._inner.store_original(source_file, relative_path, content_hash)

    def absolute(self, relative_path: str) -> Path:
        return self._inner.absolute(relative_path)

    def free_bytes(self) -> int:
        return self._inner.free_bytes()

    def exclusive_import(self) -> AbstractContextManager[None]:
        return self._inner.exclusive_import()
