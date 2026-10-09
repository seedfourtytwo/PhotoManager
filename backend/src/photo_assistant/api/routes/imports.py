from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from photo_assistant.api.deps import ADMIN_ONLY, ServicesDep
from photo_assistant.api.schemas import Id
from photo_assistant.domain.model import Outcome

REPORT_PAGE_DEFAULT, REPORT_PAGE_MAX = 500, 2000  # files of a run in one answer

router = APIRouter(prefix="/api/imports", tags=["imports"], dependencies=ADMIN_ONLY)


@router.get("")
def list_imports(services: ServicesDep, source_id: Id | None = None) -> list[dict[str, object]]:
    return services.repo.list_import_runs(source_id)


@router.get("/{run_id}")
def get_import(
    services: ServicesDep,
    run_id: int,
    outcome: Outcome | None = None,
    limit: Annotated[int, Query(ge=1, le=REPORT_PAGE_MAX)] = REPORT_PAGE_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    """One page of a run's files (a rescan of a big folder has 100,000 of them), what needs
    a look first. ``total`` counts the files of ``outcome``; the summary is the whole run's."""
    run = services.repo.get_import_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import run not found")
    items, total = services.repo.import_items_page(run_id, outcome, limit, offset)
    end = offset + len(items)
    return {
        "id": run_id,
        "source_id": run["source_id"],
        "status": run["status"],
        "message": run["message"],
        # the saved counts: an old run's file list is pruned, its summary is not
        "summary": run["summary"],
        "items": [
            {
                "relative_path": i.relative_path,
                "outcome": i.outcome.value,
                "reason": i.reason,
                "asset_id": i.asset_id,
            }
            for i in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_offset": end if end < total else None,
    }
