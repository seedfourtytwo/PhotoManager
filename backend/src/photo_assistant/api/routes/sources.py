from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from photo_assistant.api.deps import ServicesDep, require_source
from photo_assistant.api.schemas import Queued, SourceIn, SourceOut, SourcePatch
from photo_assistant.api.services import SCAN_JOB, overlaps

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources(services: ServicesDep) -> list[SourceOut]:
    return [SourceOut.of(s) for s in services.repo.list_sources()]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_source(services: ServicesDep, body: SourceIn) -> SourceOut:
    folder = Path(body.path).expanduser()
    if not folder.is_dir():
        raise HTTPException(422, f"not a folder on this machine: {folder}")
    if overlaps(folder, services.settings.data_root.expanduser()):
        raise HTTPException(422, "that folder contains, or is inside, the photo library itself")
    try:
        source = services.repo.add_source(body.label, str(folder.resolve()))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SourceOut.of(source)


@router.patch("/{source_id}")
def patch_source(services: ServicesDep, source_id: int, body: SourcePatch) -> SourceOut:
    require_source(services, source_id)
    if body.enabled is not None:
        services.repo.set_source_enabled(source_id, body.enabled)
    return SourceOut.of(require_source(services, source_id))


@router.post("/scan-all", status_code=status.HTTP_202_ACCEPTED)
def scan_all(services: ServicesDep) -> list[Queued]:
    repo = services.repo
    return [
        Queued(job_id=repo.enqueue(SCAN_JOB, {"source_id": s.id}), source_id=s.id)
        for s in repo.list_sources()
        if s.enabled
    ]


@router.post("/{source_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def scan_source(services: ServicesDep, source_id: int) -> Queued:
    require_source(services, source_id)
    job_id = services.repo.enqueue(SCAN_JOB, {"source_id": source_id})
    return Queued(job_id=job_id, source_id=source_id)
