"""Send to a device, the receiving side: the two routes that take a link's token, not a session.

``look`` says what waits; ``collect`` sends it and uses the link up. The token always comes
in the request body (the link carries it after ``#``), so no log ever holds it. What guards
these routes instead of a session: the token (256 random bits), one answer for every token
that does not work, a limit on wrong tries, and a second check, as the sender, of what the
sender may still send.
"""

from collections.abc import Iterator
from datetime import datetime
from itertools import chain
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from photo_assistant.adapters.zip_stream import zip_stream
from photo_assistant.api.deps import ServicesDep
from photo_assistant.api.routes.downloads import attachment
from photo_assistant.api.routes.handovers import arrived_encrypted
from photo_assistant.api.send_switch import feature_on
from photo_assistant.api.services import Services
from photo_assistant.app.downloads import MEDIA_TYPES, Entry, downloadable
from photo_assistant.domain.access import User, Viewer
from photo_assistant.domain.archive_name import ids_zip_name
from photo_assistant.domain.errors import ForbiddenError
from photo_assistant.domain.export_naming import ExportOptions
from photo_assistant.domain.handover import (
    Handover,
    HandoverGoneError,
    export_options,
    file_names,
    may_travel,
)

router = APIRouter(
    prefix="/api/handovers", tags=["send to a device"], dependencies=[Depends(feature_on)]
)

_FORMS = ("application/x-www-form-urlencoded", "multipart/form-data")


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class Waiting(BaseModel):
    count: int
    sent_by: str  # the sender's display name; nothing else about the library is said
    expires_at: datetime
    encrypted: bool
    details_removed: bool


class NotEncryptedError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            "this link only works over https, and it has now been cancelled because it was "
            "opened without; ask for a new one"
        )


async def presented_token(request: Request) -> str:
    """The token, from a JSON body or from a form field (the page posts a real form, so the
    browser saves the stream straight to disk). Never from the address."""
    try:
        if request.headers.get("content-type", "").startswith(_FORMS):
            raw = (await request.form()).get("token")
            return TokenIn(token=raw if isinstance(raw, str) else "").token
        return TokenIn.model_validate_json(await request.body()).token
    except ValidationError as exc:
        raise HandoverGoneError() from exc  # no token is a token that does not work


Token = Annotated[str, Depends(presented_token)]


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _waiting(services: Services, request: Request, token: str) -> Handover:
    handover = services.handovers.find(token, _client(request))  # 404 (one answer) / 429
    if not may_travel(handover, arrived_encrypted=arrived_encrypted(request)):
        # the sender was told this link is encrypted, and its token just crossed in the clear
        services.handovers.burn(handover)
        raise NotEncryptedError()
    return handover


def _sender(services: Services, handover: Handover) -> User:
    user = services.accounts.get_user(handover.created_by)
    if user is None or user.disabled:
        raise HandoverGoneError()
    return user


def _entries(services: Services, handover: Handover, options: ExportOptions) -> list[Entry]:
    """What the sender may send NOW, in the order chosen: access is checked again here, as
    the sender, because it may have been taken away since the link was made."""
    viewer = Viewer.of(_sender(services, handover))
    allowed = {
        v.id: v for v in downloadable(services.repo.views_by_ids(viewer, handover.asset_ids))
    }
    views = [allowed[i] for i in handover.asset_ids if i in allowed]
    if not views:
        raise HandoverGoneError()
    original = services.repo.first_origin_names(viewer, [v.id for v in views])
    names = [original.get(v.id, "photo") for v in views]
    return services.downloads.plan(
        views, file_names(names, details_removed=handover.details_removed), options
    )


@router.post("/look")
def look(services: ServicesDep, request: Request, token: Token) -> Waiting:
    """What this link holds. Uses nothing up: a link preview or a scanner's prefetch never
    gets this far (it has no token), and a person only reads the page."""
    handover = _waiting(services, request, token)
    options = export_options(details_removed=handover.details_removed)
    return Waiting(
        count=len(_entries(services, handover, options)),
        sent_by=_sender(services, handover).display_name,
        expires_at=handover.expires_at,
        encrypted=handover.encrypted,
        details_removed=handover.details_removed,
    )


@router.post("/collect")
def collect(services: ServicesDep, request: Request, token: Token) -> StreamingResponse:
    """The photos: one as a file, several as a streamed ZIP, and the link is used up."""
    handover = _waiting(services, request, token)
    options = export_options(details_removed=handover.details_removed)
    entries = _entries(services, handover, options)
    client, agent = _client(request), request.headers.get("user-agent")
    skipped = {"X-Skipped": str(len(handover.asset_ids) - len(entries))}
    if len(entries) == 1:
        entry = entries[0]
        content = services.downloads.content(entry.view, options)
        first = next(content, b"")  # made before the link is used up: a photo that cannot
        try:  # be produced leaves the link good for another try
            services.handovers.collect(handover, client, agent)
        except HandoverGoneError:
            _close(content)
            raise
        return StreamingResponse(
            chain((first,), content),
            media_type=MEDIA_TYPES[options.format],
            headers={"Content-Disposition": attachment(entry.name), **skipped},
        )
    services.handovers.collect(handover, client, agent)
    files = ((e.name, services.downloads.content(e.view, options)) for e in entries)
    return StreamingResponse(
        zip_stream(files),
        media_type="application/zip",
        headers={"Content-Disposition": attachment(ids_zip_name(len(entries))), **skipped},
    )


def _close(content: Iterator[bytes]) -> None:
    """Stop a download that will not be sent, so its temporary file is removed now."""
    close = getattr(content, "close", None)
    if close is not None:
        close()
