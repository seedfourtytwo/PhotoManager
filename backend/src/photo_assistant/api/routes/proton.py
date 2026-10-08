"""Proton Drive sources: is the machine signed in, which folders are there, add a source.

The sign-in itself happens in Proton's own tool on this machine (a browser login); nothing here
takes or stores account details. Pulling uses the ordinary remote-source and source routes.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from photo_assistant.api.deps import ADMIN_ONLY
from photo_assistant.api.integrations import IntegrationsDep
from photo_assistant.app.sync_source import add_proton_source
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


def _failure(exc: Exception) -> HTTPException:
    if isinstance(exc, RemoteConfigError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
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
    except (RemoteConfigError, SyncError) as exc:
        raise _failure(exc) from exc


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def add(body: ProtonSourceIn, integrations: IntegrationsDep) -> ProtonSourceOut:
    try:
        source_id = add_proton_source(
            integrations.remote_sources,
            integrations.proton,
            integrations.staging_root,
            body.label,
            body.path,
        )
    except (RemoteConfigError, SyncError) as exc:
        raise _failure(exc) from exc
    return ProtonSourceOut(id=source_id, label=body.label, path=body.path)
