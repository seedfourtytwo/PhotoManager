from fastapi import APIRouter, HTTPException, status

from photo_assistant.api.deps import ADMIN_ONLY, ServicesDep
from photo_assistant.domain.model import Outcome

router = APIRouter(prefix="/api/imports", tags=["imports"], dependencies=ADMIN_ONLY)


@router.get("")
def list_imports(services: ServicesDep, source_id: int | None = None) -> list[dict[str, object]]:
    return services.repo.list_import_runs(source_id)


@router.get("/{run_id}")
def get_import(
    services: ServicesDep, run_id: int, outcome: Outcome | None = None
) -> dict[str, object]:
    report = services.repo.get_import_report(run_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import run not found")
    items = [i for i in report.items if outcome is None or i.outcome is outcome]
    return {
        "id": run_id,
        "source_id": report.source_id,
        "status": report.status.value,
        "message": report.message,
        "summary": report.summary(),
        "items": [
            {
                "relative_path": i.relative_path,
                "outcome": i.outcome.value,
                "reason": i.reason,
                "asset_id": i.asset_id,
            }
            for i in items
        ],
    }
