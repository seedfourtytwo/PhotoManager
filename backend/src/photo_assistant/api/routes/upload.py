"""Uploads into the caller's inbox, the "what's new?" hash check, and device tokens.

Authentication (api-v1 conventions): the browser's session cookie, or
``Authorization: Bearer <device token>`` for clients like Apple Shortcuts. A device token may
upload and check, never manage devices. Cookie sessions come from the core auth module through
``app.state.session_user_hook`` (docs/wiring/ai-sources.md); ``app.state.uploader_hook`` then
says whether that account may upload at all (core roles: guests view and download only).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.concurrency import run_in_threadpool

from photo_assistant.api.integrations import IntegrationsDep
from photo_assistant.api.upload_stream import UploadReceiver
from photo_assistant.ports.upload import Device

router = APIRouter(prefix="/api", tags=["upload"])

SessionHook = Callable[[Request], int | None]
# user id -> None (no such active account), False (may not upload), True (may upload)
UploaderHook = Callable[[int], bool | None]
_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


# --- authentication --------------------------------------------------------------------------


def session_user_id(request: Request) -> int | None:
    """The signed-in user of the session cookie, via the hook the integrator installs."""
    hook: SessionHook | None = getattr(request.app.state, "session_user_hook", None)
    return hook(request) if hook is not None else None


SessionUser = Annotated[int | None, Depends(session_user_id)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers=_BEARER_CHALLENGE)


def _may_upload(request: Request, user_id: int) -> int:
    hook: UploaderHook | None = getattr(request.app.state, "uploader_hook", None)
    allowed = True if hook is None else hook(user_id)
    if allowed is None:
        raise _unauthorized("this account is disabled")
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "guests can view and download, not upload")
    return user_id


def current_user_id(request: Request, integrations: IntegrationsDep, session: SessionUser) -> int:
    """Device token if one is presented (and then it must be valid), else the session."""
    header = request.headers.get("authorization")
    if header is not None:
        scheme, _, token = header.partition(" ")
        user = integrations.devices.authenticate(token.strip())
        if scheme.lower() != "bearer" or user is None:
            raise _unauthorized("device token not valid (revoked or mistyped)")
        return _may_upload(request, user)
    if session is None:
        raise _unauthorized("sign in, or send a device token")
    return _may_upload(request, session)


def session_user_required(request: Request, session: SessionUser) -> int:
    if request.headers.get("authorization") is not None or session is None:
        raise _unauthorized("sign in to manage devices (device tokens can't)")
    return session


CurrentUser = Annotated[int, Depends(current_user_id)]
SessionOnlyUser = Annotated[int, Depends(session_user_required)]


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
async def upload(
    request: Request, user_id: CurrentUser, integrations: IntegrationsDep
) -> UploadOut:
    boundary = _boundary(request.headers.get("content-type", ""))
    receiver = UploadReceiver(integrations.upload, user_id, integrations.upload_max_files)
    try:
        await _receive(request, receiver, boundary)
    finally:
        # files already stored in the inbox are valid photos: always queue their import
        job_id = await run_in_threadpool(
            integrations.upload.finish_batch, user_id, receiver.results
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
def check(body: CheckIn, user_id: CurrentUser, integrations: IntegrationsDep) -> CheckOut:
    try:
        return CheckOut(missing=integrations.upload.missing(body.hashes))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/devices")
def list_devices(user_id: SessionOnlyUser, integrations: IntegrationsDep) -> list[DeviceOut]:
    return [DeviceOut.of(d) for d in integrations.devices.list(user_id)]


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(
    body: DeviceIn, user_id: SessionOnlyUser, integrations: IntegrationsDep
) -> NewDeviceOut:
    try:
        device, token = integrations.devices.create(user_id, body.name, body.platform)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return NewDeviceOut(device=DeviceOut.of(device), token=token)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(
    device_id: int, user_id: SessionOnlyUser, integrations: IntegrationsDep
) -> Response:
    if not integrations.devices.revoke(user_id, device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
