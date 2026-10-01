"""Admin endpoints for backups (FEATURES 9b.7, 9b.8).

Mounted by the integrator (docs/wiring/ops.md). Expects ``app.state.ops`` to be the
``OpsServices`` built with the repository as job queue, so runs go through the worker.

``require_admin`` is a PLACEHOLDER until login exists (M2): it lets every request through,
which is only acceptable while the server listens on 127.0.0.1. Replace it with the real
admin dependency (or ``app.dependency_overrides[require_admin] = real_admin``) when auth lands.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from photo_assistant.api.ops_services import OpsServices
from photo_assistant.app.backup import BackupService, UnknownTargetError
from photo_assistant.domain.backup import BackupRun, NewBackupTarget, Retention, TargetStatus
from photo_assistant.domain.schedule import InvalidScheduleError


def require_admin() -> None:
    """PLACEHOLDER: no accounts yet (M1 binds to 127.0.0.1). Swap for the real check in M2."""


def get_backup_service(request: Request) -> BackupService:
    ops: OpsServices = request.app.state.ops
    return ops.backup


BackupDep = Annotated[BackupService, Depends(get_backup_service)]
router = APIRouter(prefix="/api/backups", tags=["backups"], dependencies=[Depends(require_admin)])


class RetentionIn(BaseModel):
    daily: int = Field(default=7, ge=0)
    weekly: int = Field(default=4, ge=0)
    monthly: int = Field(default=12, ge=0)


class TargetIn(BaseModel):
    label: str
    repository: str
    password_file: str
    schedule: str = "daily 02:30"
    quiet_window: str | None = None
    retention: RetentionIn = Field(default_factory=RetentionIn)


class TargetPatch(BaseModel):
    enabled: bool


class RunOut(BaseModel):
    id: int
    kind: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    snapshot_id: str | None
    bytes_added: int | None
    files_new: int | None
    repo_bytes: int | None
    error: str | None
    details: str | None

    @classmethod
    def of(cls, run: BackupRun) -> "RunOut":
        return cls(
            id=run.id,
            kind=run.kind.value,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            snapshot_id=run.snapshot_id,
            bytes_added=run.bytes_added,
            files_new=run.files_new,
            repo_bytes=run.repo_bytes,
            error=run.error,
            details=run.details,
        )


class TargetOut(BaseModel):
    id: int
    label: str
    kind: str
    repository: str
    schedule: str
    quiet_window: str | None
    retention: dict[str, int]
    enabled: bool
    last_success_at: datetime | None
    last_run: RunOut | None
    repo_bytes: int | None
    next_run_at: datetime | None
    overdue: bool
    needs_attention: bool  # drives the warning banner

    @classmethod
    def of(cls, s: TargetStatus) -> "TargetOut":
        t = s.target
        return cls(
            id=t.id,
            label=t.label,
            kind=t.kind.value,
            repository=t.repository,
            schedule=t.schedule,
            quiet_window=t.quiet_window,
            retention=t.retention.as_dict(),
            enabled=t.enabled,
            last_success_at=s.last_success_at,
            last_run=RunOut.of(s.last_run) if s.last_run else None,
            repo_bytes=s.repo_bytes,
            next_run_at=s.next_run_at,
            overdue=s.overdue,
            needs_attention=s.needs_attention,
        )


class QueuedRun(BaseModel):
    job_id: int
    target_id: int


def _status_of(service: BackupService, target_id: int) -> TargetOut:
    for s in service.status():
        if s.target.id == target_id:
            return TargetOut.of(s)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "backup target not found")


def _known(service: BackupService, target_id: int) -> None:
    try:
        service.target(target_id)
    except UnknownTargetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backup target not found") from exc


@router.get("")
def list_backups(service: BackupDep) -> list[TargetOut]:
    return [TargetOut.of(s) for s in service.status()]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_backup(service: BackupDep, body: TargetIn) -> TargetOut:
    try:
        retention = Retention(**body.retention.model_dump())
        new = NewBackupTarget(
            body.label,
            body.repository,
            body.password_file,
            body.schedule,
            body.quiet_window,
            retention,
        )
        target = service.add_target(new)
    except (ValueError, InvalidScheduleError) as exc:
        code = status.HTTP_409_CONFLICT if "already exists" in str(exc) else 422
        raise HTTPException(code, str(exc)) from exc
    return _status_of(service, target.id)


@router.patch("/{target_id}")
def patch_backup(service: BackupDep, target_id: int, body: TargetPatch) -> TargetOut:
    _known(service, target_id)
    service.set_enabled(target_id, body.enabled)
    return _status_of(service, target_id)


@router.post("/{target_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_backup(service: BackupDep, target_id: int) -> QueuedRun:
    _known(service, target_id)
    return QueuedRun(job_id=service.queue_run(target_id), target_id=target_id)


@router.post("/{target_id}/restore-test", status_code=status.HTTP_202_ACCEPTED)
def restore_test(service: BackupDep, target_id: int) -> QueuedRun:
    _known(service, target_id)
    return QueuedRun(job_id=service.queue_restore_test(target_id), target_id=target_id)


@router.get("/{target_id}/runs")
def list_runs(service: BackupDep, target_id: int, limit: int = 50) -> list[RunOut]:
    _known(service, target_id)
    return [RunOut.of(r) for r in service.runs(target_id, min(max(limit, 1), 500))]
