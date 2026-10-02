"""Sources (the folders photos come from) and who may see them (contract: Sources)."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from photo_assistant.adapters.sqlite_access import UnknownUserError
from photo_assistant.api.deps import (
    ADMIN_ONLY,
    LOGGED_IN,
    AdminUser,
    ServicesDep,
    ViewerDep,
    require_source,
)
from photo_assistant.api.schemas import (
    Access,
    Queued,
    SourceIn,
    SourceOut,
    SourcePatch,
    UserAccess,
)
from photo_assistant.api.services import SCAN_JOB, Services
from photo_assistant.domain.access import Level, Viewer

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _out(services: Services, viewer: Viewer, source_id: int) -> SourceOut:
    for source, count in services.repo.sources_for(viewer):
        if source.id == source_id:
            return SourceOut.of(source, count)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")


@router.get("", dependencies=LOGGED_IN)
def list_sources(services: ServicesDep, viewer: ViewerDep) -> list[SourceOut]:
    """The sources you may see (all of them for an admin)."""
    return [SourceOut.of(s, n) for s, n in services.repo.sources_for(viewer)]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_source(services: ServicesDep, admin: AdminUser, body: SourceIn) -> SourceOut:
    folder = Path(body.path).expanduser()
    if not folder.is_dir():
        raise HTTPException(422, f"folder not found on this machine: {folder}")
    if services.store.overlaps(folder):
        raise HTTPException(422, "that folder contains, or is inside, the photo library itself")
    if services.ops.backup.repository_overlaps(folder):
        raise HTTPException(422, "that folder contains, or is inside, a backup repository")
    try:
        source = services.repo.add_source(body.label, str(folder.resolve()), owner_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SourceOut.of(source, 0)


@router.patch("/{source_id}")
def patch_source(
    services: ServicesDep, admin: AdminUser, viewer: ViewerDep, source_id: int, body: SourcePatch
) -> SourceOut:
    require_source(services, source_id)
    if body.enabled is not None:
        services.repo.set_source_enabled(source_id, body.enabled)
    if body.owner_id is not None:
        try:
            services.repo.set_source_owner(source_id, body.owner_id)
        except UnknownUserError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _out(services, viewer, source_id)


@router.get("/{source_id}/access", dependencies=LOGGED_IN)
def get_access(services: ServicesDep, viewer: ViewerDep, source_id: int) -> Access:
    if not services.repo.source_visible_to(viewer, source_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    everyone, users = services.repo.get_access(source_id)
    return Access(
        everyone=everyone.label if everyone else None,  # type: ignore[arg-type]
        users=[UserAccess(user_id=u, level=lvl.label) for u, lvl in users],  # type: ignore[arg-type]
    )


@router.put("/{source_id}/access", dependencies=ADMIN_ONLY)
def put_access(services: ServicesDep, viewer: ViewerDep, source_id: int, body: Access) -> Access:
    require_source(services, source_id)
    users = [(u.user_id, Level.parse(u.level)) for u in body.users]
    everyone = Level.parse(body.everyone) if body.everyone else None
    try:
        services.repo.set_access(source_id, everyone, users)
    except UnknownUserError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return get_access(services, viewer, source_id)


@router.post("/scan-all", status_code=status.HTTP_202_ACCEPTED, dependencies=ADMIN_ONLY)
def scan_all(services: ServicesDep) -> list[Queued]:
    repo = services.repo
    return [
        Queued(job_id=repo.enqueue(SCAN_JOB, {"source_id": s.id}), source_id=s.id)
        for s in repo.list_sources()
        if s.enabled
    ]


@router.post("/{source_id}/scan", status_code=status.HTTP_202_ACCEPTED, dependencies=ADMIN_ONLY)
def scan_source(services: ServicesDep, source_id: int) -> Queued:
    require_source(services, source_id)
    job_id = services.repo.enqueue(SCAN_JOB, {"source_id": source_id})
    return Queued(job_id=job_id, source_id=source_id)
