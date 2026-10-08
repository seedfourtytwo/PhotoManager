"""Browse the folders of the machine the app runs on, to pick one (issue 7).

Admin only and read-only: names of folders, never files. The library's own folder is never
listed or opened; ``source_problem`` says why the folder shown can't become a source.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from photo_assistant.adapters.folder_listing import FolderUnavailableError, LocalFolders
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


@router.get("")
def list_folders(
    services: ServicesDep, path: Annotated[str | None, Query(max_length=8192)] = None
) -> FolderListingOut:
    home = Path.home()
    if path is not None and (problem := folder_path_problem(path)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    folder = (Path(path) if path is not None else home).resolve()
    if _inside_library(services, folder):  # before looking: nothing in there is ever listed
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, LIBRARY_ITSELF)
    try:
        listing = LocalFolders().list(folder)
    except FolderUnavailableError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
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
