"""Uploads into the caller's inbox, the "what's new?" hash check, and device tokens.

Authentication (api-v1 conventions): the browser's session cookie, or
``Authorization: Bearer <device token>`` for clients like Apple Shortcuts, resolved by one
dependency in ``api/deps.py`` (fails closed; guests 403). A device token may upload and check,
never manage devices.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.concurrency import run_in_threadpool

from photo_assistant.api.deps import ServicesDep, SessionOnlyUser, UploaderUser
from photo_assistant.api.upload_stream import UploadReceiver
from photo_assistant.domain.access import Viewer
from photo_assistant.ports.upload import Device

router = APIRouter(prefix="/api", tags=["upload"])


# --- schemas ---------------------------------------------------------------------------------


class UploadedFile(BaseModel):
    name: str
    outcome: str  # stored | duplicate | rejected
    stored_as: str | None
    content_hash: str | None
    asset_id: int | None
    reason: str | None


class UploadOut(BaseModel):
    files: list[UploadedFile]
    import_job_id: int | None


class CheckIn(BaseModel):
    hashes: list[str] = Field(max_length=5000)


class CheckOut(BaseModel):
    missing: list[str]


class DeviceIn(BaseModel):
    name: str
    platform: str = "other"


class DeviceOut(BaseModel):
    id: int
    name: str
    platform: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool

    @classmethod
    def of(cls, d: Device) -> "DeviceOut":
        return cls(
            id=d.id,
            name=d.name,
            platform=d.platform,
            created_at=d.created_at,
            last_used_at=d.last_used_at,
            revoked=d.revoked_at is not None,
        )


class NewDeviceOut(BaseModel):
    device: DeviceOut
    token: str  # shown once; store it in the Shortcut / app now


# --- routes ----------------------------------------------------------------------------------


def _boundary(content_type: str) -> bytes:
    kind, params = parse_options_header(content_type)
    if kind != b"multipart/form-data":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "send the photos as multipart/form-data"
        )
    boundary = params.get(b"boundary")
    if not boundary:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "multipart upload without a boundary")
    return boundary


async def _receive(request: Request, receiver: UploadReceiver, boundary: bytes) -> None:
    parser = MultipartParser(boundary, receiver.callbacks())  # type: ignore[arg-type]
    try:
        async for chunk in request.stream():
            await run_in_threadpool(parser.write, chunk)
    except MultipartParseError as exc:
        receiver.abort()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"broken upload: {exc}") from exc
    except BaseException:
        receiver.abort()
        raise
    if not receiver.complete:
        receiver.abort()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the upload ended before it was complete")


@router.post("/upload")
async def upload(request: Request, user: UploaderUser, services: ServicesDep) -> UploadOut:
    integrations = services.integrations
    boundary = _boundary(request.headers.get("content-type", ""))
    receiver = UploadReceiver(integrations.upload, Viewer.of(user), integrations.upload_max_files)
    try:
        await _receive(request, receiver, boundary)
    finally:
        # files already stored in the inbox are valid photos: always queue their import
        job_id = await run_in_threadpool(
            integrations.upload.finish_batch, user.id, receiver.results
        )
    files = [
        UploadedFile(
            name=r.name,
            outcome=r.outcome.value,
            stored_as=r.stored_as,
            content_hash=r.content_hash,
            asset_id=r.asset_id,
            reason=r.reason,
        )
        for r in receiver.results
    ]
    return UploadOut(files=files, import_job_id=job_id)


@router.post("/upload/check")
def check(body: CheckIn, user: UploaderUser, services: ServicesDep) -> CheckOut:
    """The hashes *this user* lacks: purged photos count as present; photos that exist but
    are hidden from them are missing (uploading links them to their inbox)."""
    try:
        return CheckOut(missing=services.integrations.upload.missing(Viewer.of(user), body.hashes))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/devices")
def list_devices(user: SessionOnlyUser, services: ServicesDep) -> list[DeviceOut]:
    return [DeviceOut.of(d) for d in services.integrations.devices.list(user.id)]


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(body: DeviceIn, user: SessionOnlyUser, services: ServicesDep) -> NewDeviceOut:
    try:
        device, token = services.integrations.devices.create(user.id, body.name, body.platform)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return NewDeviceOut(device=DeviceOut.of(device), token=token)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: int, user: SessionOnlyUser, services: ServicesDep) -> Response:
    if not services.integrations.devices.revoke(user.id, device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
