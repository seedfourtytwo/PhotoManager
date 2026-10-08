"""Browse the folders of the machine the app runs on, to pick one (issue 7).

Admin only. Listing is read-only: names of folders, never files. The library's own folder is
never listed or opened; ``source_problem`` says why the folder shown can't become a source.
A new, empty folder can be created inside an existing one (never inside the library).
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from photo_assistant.adapters.folder_listing import (
    FolderMissingError,
    FolderUnavailableError,
    LocalFolders,
)
from photo_assistant.api.deps import ADMIN_ONLY, ServicesDep
from photo_assistant.api.services import Services
from photo_assistant.domain.library_paths import folder_path_problem

router = APIRouter(prefix="/api/folders", tags=["folders"], dependencies=ADMIN_ONLY)

LIBRARY_ITSELF = "that is the photo library itself: choose the folder your photos come from"


class FolderOut(BaseModel):
    name: str
    path: str


class RootOut(BaseModel):
    label: str
    path: str


class FolderListingOut(BaseModel):
    path: str
    parent: str | None
    folders: list[FolderOut]
    truncated: bool
    roots: list[RootOut]  # places to start from: the home folder, plugged-in disks
    source_problem: str | None  # why this folder can't be added as a source


def source_problem(services: Services, folder: Path) -> str | None:
    """Why ``folder`` (resolved) can't be a source. The one check, for browsing and adding."""
    if services.store.overlaps(folder):
        return "this folder contains the photo library itself"
    if services.ops.backup.repository_overlaps(folder):
        return "this folder holds a backup"
    for source in services.repo.list_sources():
        if source.kind == "folder" and Path(source.root) == folder:
            return f"already added as “{source.label}”"
    return None


def _inside_library(services: Services, folder: Path) -> bool:
    root = services.store.root.resolve()
    return folder == root or root in folder.parents


class NewFolder(BaseModel):
    path: str = Field(max_length=8192)


def _checked(services: Services, path: str) -> Path:
    """The resolved folder for a path from a person, or a 422 saying what is wrong with it."""
    if problem := folder_path_problem(path):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    folder = Path(path).resolve()
    if _inside_library(services, folder):  # before looking: nothing in there is ever listed
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, LIBRARY_ITSELF)
    return folder


def _listing(services: Services, folder: Path) -> FolderListingOut:
    try:
        listing = LocalFolders().list(folder)
    except FolderMissingError as exc:  # its own status: the app offers to create it
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except FolderUnavailableError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    home = Path.home()
    disks = services.ops.backup.disks()
    return FolderListingOut(
        path=listing.path,
        parent=listing.parent,
        folders=[
            FolderOut(name=f.name, path=f.path)
            for f in listing.folders
            if not _inside_library(services, Path(f.path))
        ],
        truncated=listing.truncated,
        roots=[
            RootOut(label="Home", path=str(home.resolve())),
            *(RootOut(label=d.label, path=d.path) for d in disks),
        ],
        source_problem=source_problem(services, folder),
    )


@router.get("")
def list_folders(
    services: ServicesDep, path: Annotated[str | None, Query(max_length=8192)] = None
) -> FolderListingOut:
    folder = _checked(services, path) if path is not None else Path.home().resolve()
    if _inside_library(services, folder):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, LIBRARY_ITSELF)
    return _listing(services, folder)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_folder(services: ServicesDep, body: NewFolder) -> FolderListingOut:
    """Make one new, empty folder inside an existing one, and show it."""
    folder = _checked(services, body.path)
    try:
        created = LocalFolders().create(folder)
    except FolderUnavailableError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _listing(services, created)
