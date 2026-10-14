"""Sources (the folders photos come from) and who may see them (contract: Sources)."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

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
    SourceRemoval,
    SourceRemoved,
    UserAccess,
)
from photo_assistant.api.services import Services
from photo_assistant.app.enrich import FULL_REGROUP, GROUP_JOB
from photo_assistant.app.stop_watching import PhotosOnlyHere
from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.domain.access import KEPT_KIND, Level, Viewer
from photo_assistant.domain.library_paths import folder_path_problem
from photo_assistant.domain.model import Source
from photo_assistant.domain.recheck import Recheck
from photo_assistant.domain.remote_source import PROTON, RCLONE, RemoteConfigError

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _problem(source: Source) -> str | None:
    """What stops a rescan, shown next to the source (QA A13). A remote source's staging
    folder only exists after its first pull, so it is never "not found"."""
    if source.kind not in (RCLONE, PROTON, KEPT_KIND) and not Path(source.root).is_dir():
        return "folder not found"
    return None


def _place(services: Services, source: Source) -> str | None:
    """Where a remote source reads from (None for folders, and for damaged settings)."""
    if source.kind not in (RCLONE, PROTON):
        return None
    try:
        config = services.integrations.remote_sources.remote_config(source.id)
    except RemoteConfigError:
        return None
    return config.place if config else None


def _outs(services: Services, viewer: Viewer) -> list[SourceOut]:
    next_checks = services.rechecks.next_checks()
    return [
        SourceOut.of(s, n, viewer.is_admin, _problem(s), _place(services, s), next_checks.get(s.id))
        for s, n in services.repo.sources_for(viewer)
    ]


def _out(services: Services, viewer: Viewer, source_id: int) -> SourceOut:
    for out in _outs(services, viewer):
        if out.id == source_id:
            return out
    raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")


@router.get("", dependencies=LOGGED_IN)
def list_sources(services: ServicesDep, viewer: ViewerDep) -> list[SourceOut]:
    """The sources you may see (all of them for an admin)."""
    return _outs(services, viewer)


@router.post("", status_code=status.HTTP_201_CREATED)
def add_source(services: ServicesDep, admin: AdminUser, body: SourceIn) -> SourceOut:
    if problem := folder_path_problem(str(Path(body.path).expanduser())):
        raise HTTPException(422, problem)
    folder = Path(body.path).expanduser()
    if not folder.is_dir():
        raise HTTPException(422, f"folder not found on this machine: {folder}")
    if services.store.overlaps(folder):
        raise HTTPException(422, "that folder contains, or is inside, the photo library itself")
    if services.ops.backup.repository_overlaps(folder):
        raise HTTPException(422, "that folder contains, or is inside, a backup repository")
    source = services.repo.add_source(body.label, str(folder.resolve()), owner_id=admin.id)
    return SourceOut.of(source, 0, show_path=True)


@router.patch("/{source_id}")
def patch_source(
    services: ServicesDep, admin: AdminUser, viewer: ViewerDep, source_id: int, body: SourcePatch
) -> SourceOut:
    require_source(services, source_id)
    if body.enabled or (body.recheck is not None and body.recheck is not Recheck.OFF):
        services.stop_watching.require_watchable(source_id)
    if body.enabled is not None:
        services.repo.set_source_enabled(source_id, body.enabled)
    if body.label is not None:
        services.repo.rename_source(source_id, body.label)
    if body.owner_id is not None:
        services.repo.set_source_owner(source_id, body.owner_id)  # unknown user: 422
    if body.recheck is not None:
        services.repo.set_source_recheck(source_id, body.recheck)
    return _out(services, viewer, source_id)


@router.get("/{source_id}/removal", dependencies=ADMIN_ONLY)
def removal(services: ServicesDep, source_id: int) -> SourceRemoval:
    """What "Stop watching" would do: the confirm sheet shows it before anything changes."""
    preview = services.stop_watching.preview(source_id)
    return SourceRemoval(photos=preview.photos, only_here=preview.only_here)


@router.delete("/{source_id}")
def remove_source(
    services: ServicesDep,
    admin: AdminUser,
    source_id: int,
    photos: Annotated[PhotosOnlyHere, Query()] = PhotosOnlyHere.KEEP,
) -> SourceRemoved:
    """Stop watching a folder. ``keep`` detaches it (everyone keeps seeing its photos); on a
    source already detached, or with ``trash``, it is removed. Never touches the folder."""
    removed = services.stop_watching.stop(source_id, photos, admin.id)
    if removed.trashed:
        services.repo.enqueue_once(GROUP_JOB, FULL_REGROUP)  # groups lose members
    return SourceRemoved(
        only_here=removed.only_here, trashed=removed.trashed, detached=removed.detached
    )


@router.get("/{source_id}/access", dependencies=ADMIN_ONLY)
def get_access(services: ServicesDep, source_id: int) -> Access:
    """Who may see a source: the admin's business only (v1.2, QA A12)."""
    require_source(services, source_id)
    everyone, users = services.repo.get_access(source_id)
    return Access(
        everyone=everyone.label if everyone else None,  # type: ignore[arg-type]
        users=[UserAccess(user_id=u, level=lvl.label) for u, lvl in users],  # type: ignore[arg-type]
    )


@router.put("/{source_id}/access", dependencies=ADMIN_ONLY)
def put_access(services: ServicesDep, source_id: int, body: Access) -> Access:
    require_source(services, source_id)
    users = [(u.user_id, Level.parse(u.level)) for u in body.users]
    everyone = Level.parse(body.everyone) if body.everyone else None
    services.repo.set_access(source_id, everyone, users)  # unknown user: 422
    return get_access(services, source_id)


@router.post("/scan-all", status_code=status.HTTP_202_ACCEPTED, dependencies=ADMIN_ONLY)
def scan_all(services: ServicesDep) -> list[Queued]:
    repo = services.repo
    return [
        Queued(job_id=repo.enqueue(SCAN_JOB_KIND, {"source_id": s.id}), source_id=s.id)
        for s in repo.list_sources()
        if s.enabled
    ]


@router.post("/{source_id}/scan", status_code=status.HTTP_202_ACCEPTED, dependencies=ADMIN_ONLY)
def scan_source(services: ServicesDep, source_id: int) -> Queued:
    services.stop_watching.require_watchable(source_id)
    job_id = services.repo.enqueue(SCAN_JOB_KIND, {"source_id": source_id})
    return Queued(job_id=job_id, source_id=source_id)
