from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from photo_assistant import __version__
from photo_assistant.api.deps import ServicesDep

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/stats")
def stats(services: ServicesDep) -> dict[str, object]:
    return {
        "assets": services.repo.count_assets(),
        "sources": len(services.repo.list_sources()),
        "jobs": services.repo.job_counts(),
        "free_bytes": services.store.free_bytes(),
    }


@router.get("/jobs")
def list_jobs(
    services: ServicesDep, status_filter: Annotated[str | None, Query(alias="status")] = None
) -> list[dict[str, object]]:
    return services.repo.list_jobs(status_filter)


@router.post("/jobs/{job_id}/retry")
def retry_job(services: ServicesDep, job_id: int) -> dict[str, bool]:
    if not services.repo.retry_job(job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no failed job with that id")
    return {"queued": True}
