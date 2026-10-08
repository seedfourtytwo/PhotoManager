"""Proton Drive: is the machine signed in, which folders are there, add a source, make a
folder (for a backup copy).

The sign-in itself happens in Proton's own tool on this machine (a browser login); nothing here
takes or stores account details. Pulling uses the ordinary remote-source and source routes.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from photo_assistant.api.deps import ADMIN_ONLY, AdminUser, IntegrationsDep
from photo_assistant.app.sync_source import add_proton_source, create_proton_folder
from photo_assistant.domain.remote_source import PROTON_PHOTOS, RemoteConfig, RemoteConfigError
from photo_assistant.ports.sync import SyncError, SyncNotFoundError

router = APIRouter(prefix="/api/proton", tags=["sources"], dependencies=ADMIN_ONLY)


class ProtonStatus(BaseModel):
    ready: bool
    problem: str | None  # what to do when not ready


class ProtonFolders(BaseModel):
    path: str
    folders: list[str]


class ProtonSourceIn(BaseModel):
    label: str
    path: str


class ProtonSourceOut(BaseModel):
    id: int
    label: str
    path: str


def _failure(exc: SyncError) -> HTTPException:
    """Proton could not do it. Sync errors stay outside the DomainError hierarchy (a pull that
    fails for one of them is retried by the worker), so the route gives them their status."""
    if isinstance(exc, SyncNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.get("")
def proton_status(integrations: IntegrationsDep) -> ProtonStatus:
    try:
        integrations.proton.check()
    except SyncError as exc:
        return ProtonStatus(ready=False, problem=str(exc))
    return ProtonStatus(ready=True, problem=None)


@router.get("/folders")
def folders(path: str, integrations: IntegrationsDep) -> ProtonFolders:
    """The folders inside a place in My files (the Photos section has none to choose)."""
    try:
        if path == PROTON_PHOTOS:
            raise RemoteConfigError("the Photos section has no folders to choose from")
        RemoteConfig.proton(path)
        return ProtonFolders(path=path, folders=integrations.proton.folders(path))
    except SyncError as exc:
        raise _failure(exc) from exc


class NewProtonFolder(BaseModel):
    parent: str
    name: str


@router.post("/folders", status_code=status.HTTP_201_CREATED)
def create_folder(body: NewProtonFolder, integrations: IntegrationsDep) -> ProtonFolders:
    """Make a new, empty folder in My files (a place for a backup copy) and show it."""
    try:
        path = create_proton_folder(integrations.proton, body.parent, body.name)
    except SyncError as exc:
        raise _failure(exc) from exc
    return ProtonFolders(path=path, folders=[])


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def add(body: ProtonSourceIn, integrations: IntegrationsDep, admin: AdminUser) -> ProtonSourceOut:
    try:
        source_id = add_proton_source(
            integrations.remote_sources,
            integrations.proton,
            integrations.staging_root,
            body.label,
            body.path,
            admin.id,
        )
    except SyncError as exc:
        raise _failure(exc) from exc
    return ProtonSourceOut(id=source_id, label=body.label, path=body.path)
