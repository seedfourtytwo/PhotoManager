"""Send to a device, the sender's side: make a one-time link, watch it, cancel it, read the trail.

Off unless ``PA_SEND_TO_DEVICE=true``: until then ``create_app`` does not mount these routes,
so they answer 404 like any address the app does not know. Members and admins only; a
guest never sends. The receiving device's two routes, which take no session, are in
``receive.py``.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from photo_assistant.api.deps import MemberUser, ServicesDep, require_views
from photo_assistant.api.routes.testing import is_loopback
from photo_assistant.api.schemas import Id
from photo_assistant.api.send_switch import feature_on
from photo_assistant.api.services import Services
from photo_assistant.api.settings import Settings
from photo_assistant.domain.access import Level, User, Viewer
from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.handover import (
    MAX_BYTES,
    MAX_PHOTOS,
    Handover,
    export_options,
    unique_ids,
)

RECEIVE_PAGE = "/receive.html"
Via = Literal["here", "home"]


router = APIRouter(
    prefix="/api/handovers", tags=["send to a device"], dependencies=[Depends(feature_on)]
)


class NoAddressError(InvalidError):
    """The link would carry an address the other device cannot open."""


class LinkAddress(BaseModel):
    via: Via  # here: the address the sender is using; home: PA_SEND_TO_DEVICE_ADDRESS
    origin: str
    encrypted: bool


class HandoverOptions(BaseModel):
    addresses: list[LinkAddress]  # none: no other device can reach this library as it is run
    unencrypted_allowed: bool
    remove_details: bool  # what the dialog's switch starts as
    minutes: int
    max_photos: int = MAX_PHOTOS
    max_bytes: int = MAX_BYTES


class HandoverIn(BaseModel):
    ids: list[Id] = Field(min_length=1, max_length=10 * MAX_PHOTOS)
    via: Via
    remove_details: bool
    unencrypted_ok: bool = False  # the sender read the warning and chose "Send anyway"


class SentBy(BaseModel):
    id: int
    display_name: str


class HandoverOut(BaseModel):
    id: int
    state: str
    count: int
    bytes: int
    created_at: datetime
    expires_at: datetime
    encrypted: bool
    details_removed: bool
    sent_by: SentBy
    redeemed_at: datetime | None
    redeemed_from: str | None
    redeemed_agent: str | None


class HandoverCreated(HandoverOut):
    url: str  # the link, with its token: shown this once, stored nowhere


def arrived_encrypted(request: Request) -> bool:
    """Whether this request came in over https, as the server itself knows it: uvicorn sets
    the scheme from ``X-Forwarded-Proto`` only when the request comes from an address in
    ``PA_TRUSTED_PROXIES`` (the https proxy in front). Anything else is plain http, whatever
    its headers say; when in doubt it is not encrypted."""
    return request.url.scheme == "https"


def link_addresses(request: Request, settings: Settings) -> list[LinkAddress]:
    """Where a link may point: the address the sender is using, unless it is this machine's
    own (no other device can open ``localhost``), and the home address an admin set."""
    found = []
    if not is_loopback(request.url.hostname or "localhost"):
        here = f"{request.url.scheme}://{request.url.netloc}"
        found.append(LinkAddress(via="here", origin=here, encrypted=arrived_encrypted(request)))
    home = settings.send_to_device_address
    if home is not None and home not in [a.origin for a in found]:
        found.append(LinkAddress(via="home", origin=home, encrypted=home.startswith("https://")))
    return found


def _address(request: Request, settings: Settings, via: Via) -> LinkAddress:
    for address in link_addresses(request, settings):
        if address.via == via:
            return address
    raise NoAddressError(
        "other devices cannot open the address you are using; an admin can set one they "
        "can (PA_SEND_TO_DEVICE_ADDRESS)"
    )


def _out(services: Services, handover: Handover, names: dict[int, str]) -> HandoverOut:
    return HandoverOut(
        id=handover.id,
        state=handover.state(services.clock.now()).value,
        count=len(handover.asset_ids),
        bytes=handover.byte_size,
        created_at=handover.created_at,
        expires_at=handover.expires_at,
        encrypted=handover.encrypted,
        details_removed=handover.details_removed,
        sent_by=SentBy(id=handover.created_by, display_name=names.get(handover.created_by, "?")),
        redeemed_at=handover.redeemed_at,
        redeemed_from=handover.redeemed_from,
        redeemed_agent=handover.redeemed_agent,
    )


def _names(services: Services, user: User, handovers: list[Handover]) -> dict[int, str]:
    """Display names of the senders. A member only ever lists their own."""
    if all(h.created_by == user.id for h in handovers):
        return {user.id: user.display_name}
    return {u.id: u.display_name for u in services.accounts.list_users()}


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(_settings)]


@router.get("/options")
def options(request: Request, user: MemberUser, settings: SettingsDep) -> HandoverOptions:
    return HandoverOptions(
        addresses=link_addresses(request, settings),
        unencrypted_allowed=settings.send_to_device_unencrypted,
        remove_details=settings.send_to_device_remove_details,
        minutes=settings.send_to_device_minutes,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create(
    request: Request,
    services: ServicesDep,
    user: MemberUser,
    settings: SettingsDep,
    body: HandoverIn,
) -> HandoverCreated:
    """Every photo must be one the sender sees and may download (404 / 403 otherwise): the
    library's one visibility rule, so another person's private photos never qualify."""
    address = _address(request, settings, body.via)
    ids = list(unique_ids(body.ids))
    views = require_views(services, Viewer.of(user), ids, Level.DOWNLOAD)
    size = services.downloads.estimate(views, export_options(details_removed=body.remove_details))
    handover, token = services.handovers.create(
        user,
        ids,
        size,
        encrypted=address.encrypted,
        details_removed=body.remove_details,
        confirmed_unencrypted=body.unencrypted_ok,
    )
    out = _out(services, handover, {user.id: user.display_name})
    # after the '#': a browser never sends that part to a server, so the token is in no
    # access log, no proxy log and no Referer
    return HandoverCreated(**out.model_dump(), url=f"{address.origin}{RECEIVE_PAGE}#{token}")


@router.get("")
def trail(services: ServicesDep, user: MemberUser) -> list[HandoverOut]:
    """Newest first: an admin reads everyone's, a member their own."""
    handovers = services.handovers.list_for(user)
    names = _names(services, user, handovers)
    return [_out(services, h, names) for h in handovers]


@router.get("/{handover_id}")
def one(services: ServicesDep, user: MemberUser, handover_id: int) -> HandoverOut:
    handover = services.handovers.get_for(user, handover_id)
    return _out(services, handover, _names(services, user, [handover]))


@router.delete("/{handover_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel(services: ServicesDep, user: MemberUser, handover_id: int) -> Response:
    """Only while it still waits (409 with the reason otherwise)."""
    services.handovers.cancel(user, handover_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
