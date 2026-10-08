"""Sub-folders of one folder on this machine, for picking a folder in the web app.

Read-only: it lists names, never opens a file and never follows a link it can't resolve.
Hidden folders (dot names) are left out: nobody keeps their photos in ``.cache``.
"""

from dataclasses import dataclass
from pathlib import Path

from photo_assistant.domain.library_paths import folder_path_problem


class FolderUnavailableError(Exception):
    """The folder can't be listed; the message says why."""


@dataclass(frozen=True, slots=True)
class FolderEntry:
    name: str
    path: str


@dataclass(frozen=True, slots=True)
class FolderListing:
    path: str  # resolved: links followed
    parent: str | None  # None at the top of the disk
    folders: tuple[FolderEntry, ...]
    truncated: bool  # there were more than the limit


def _is_folder(entry: Path) -> bool:
    try:
        return entry.is_dir()
    except OSError:  # a link loop, a vanished disk
        return False


class LocalFolders:
    def __init__(self, limit: int = 1000) -> None:
        self._limit = limit

    def list(self, folder: Path) -> FolderListing:
        try:
            folder = folder.resolve()
            if not folder.exists():
                raise FolderUnavailableError(f"folder not found on this machine: {folder}")
            if not folder.is_dir():
                raise FolderUnavailableError(f"{folder} is not a folder")
            names = sorted(
                (
                    entry.name
                    for entry in folder.iterdir()
                    if not entry.name.startswith(".")
                    and folder_path_problem(str(entry)) is None
                    and _is_folder(entry)
                ),
                key=str.casefold,
            )
        except PermissionError as exc:
            raise FolderUnavailableError(f"{folder} can't be read by the app") from exc
        except OSError as exc:
            raise FolderUnavailableError(f"{folder}: {exc.strerror or exc}") from exc
        shown = names[: self._limit]
        return FolderListing(
            path=str(folder),
            parent=None if folder.parent == folder else str(folder.parent),
            folders=tuple(FolderEntry(name, str(folder / name)) for name in shown),
            truncated=len(names) > len(shown),
        )
