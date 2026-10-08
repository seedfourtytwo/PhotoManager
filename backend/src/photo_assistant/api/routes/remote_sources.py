"""Remote (rclone) sources: register one, list the remotes rclone knows, queue a pull.

Listing, scanning, enabling and access use the ordinary /api/sources routes (a remote source
is a source of kind "rclone"). Admin-only (core's admin check), like adding any source.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from photo_assistant.api.deps import ADMIN_ONLY, AdminUser, IntegrationsDep
from photo_assistant.app.sync_source import SCAN_JOB_KIND, add_remote_source

router = APIRouter(prefix="/api/remote-sources", tags=["sources"], dependencies=ADMIN_ONLY)


class RemoteSourceIn(BaseModel):
    label: str
    remote: str
    path: str = ""


class RemoteSourceOut(BaseModel):
    id: int
    label: str
    remote: str
    path: str


class RemotesOut(BaseModel):
    remotes: list[str]


class PullQueued(BaseModel):
    job_id: int
    source_id: int


@router.get("/remotes")
def list_remotes(integrations: IntegrationsDep) -> RemotesOut:
    return RemotesOut(remotes=integrations.rclone.list_remotes())


@router.post("", status_code=status.HTTP_201_CREATED)
def add(body: RemoteSourceIn, integrations: IntegrationsDep, admin: AdminUser) -> RemoteSourceOut:
    source_id = add_remote_source(
        integrations.remote_sources,
        integrations.rclone,
        integrations.staging_root,
        body.label,
        {"remote": body.remote, "path": body.path},
        admin.id,
    )
    return RemoteSourceOut(id=source_id, label=body.label, remote=body.remote, path=body.path)


@router.post("/{source_id}/pull", status_code=status.HTTP_202_ACCEPTED)
def pull(source_id: int, integrations: IntegrationsDep) -> PullQueued:
    if integrations.remote_sources.remote_config(source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no remote source with that id")
    job_id = integrations.repo.enqueue(SCAN_JOB_KIND, {"source_id": source_id})
    return PullQueued(job_id=job_id, source_id=source_id)
