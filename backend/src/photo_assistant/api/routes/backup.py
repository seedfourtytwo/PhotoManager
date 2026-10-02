"""Admin endpoints for backups (FEATURES 9b.7, 9b.8).

Expects ``app.state.ops`` to be the ``OpsServices`` built with the repository as job queue,
so runs go through the worker. Every route is admin-only (core's session auth and roles).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from photo_assistant.api.deps import ADMIN_ONLY
from photo_assistant.api.ops_services import OpsServices
from photo_assistant.app.backup import BackupService, UnknownTargetError
from photo_assistant.domain.backup import (
    BackupRun,
    NewBackupTarget,
    Retention,
    TargetSettings,
    TargetStatus,
)
from photo_assistant.domain.schedule import InvalidScheduleError


def get_backup_service(request: Request) -> BackupService:
    ops: OpsServices = request.app.state.ops
    return ops.backup


BackupDep = Annotated[BackupService, Depends(get_backup_service)]
router = APIRouter(prefix="/api/backups", tags=["backups"], dependencies=ADMIN_ONLY)


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


class RetentionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily: int | None = Field(default=None, ge=0)
    weekly: int | None = Field(default=None, ge=0)
    monthly: int | None = Field(default=None, ge=0)


class TargetPatch(BaseModel):
    """Only the fields sent change (v1.3); ``quiet_window: null`` means "any time"."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    schedule: str | None = None
    quiet_window: str | None = None
    retention: RetentionPatch | None = None

    def settings(self, current: TargetSettings) -> TargetSettings | None:
        """The new settings, or None when none were sent. Raises on bad values."""
        sent = self.model_fields_set & {"schedule", "quiet_window", "retention"}
        if not sent:
            return None
        if "schedule" in sent and self.schedule is None:
            raise InvalidScheduleError("the schedule can't be empty: use 'manual' to pause it")
        kept = current.retention.as_dict()
        if self.retention is not None:
            kept |= self.retention.model_dump(exclude_none=True)
        return TargetSettings(
            self.schedule if self.schedule is not None else current.schedule,
            self.quiet_window if "quiet_window" in sent else current.quiet_window,
            Retention(**kept),
        )


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
    try:
        settings = body.settings(service.target(target_id).settings)
    except (ValueError, InvalidScheduleError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if settings is not None:
        service.change_settings(target_id, settings)
    if body.enabled is not None:
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
