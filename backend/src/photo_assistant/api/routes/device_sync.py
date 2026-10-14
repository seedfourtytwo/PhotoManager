"""Keep on my phone (contract: "Keep on my phone"; FEATURES 10.6; app/device_sync.py).

Two callers, never mixed:
- a signed-in browser chooses what each of the person's devices keeps (``/api/devices/{id}/sync``);
- the device itself, with ``Authorization: Bearer <its token>`` and nothing else, reads its
  list (``/api/sync/manifest``), fetches originals on it (``/api/sync/assets/{id}/original``)
  and says which it saved.
  It changes nothing in the library: it only says which photos it saved
  (``/api/sync/sent``), and what it deletes stays here.
"""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from photo_assistant.api.deps import DeviceOnly, ServicesDep, SessionOnlyUser
from photo_assistant.api.filters import checked
from photo_assistant.api.routes.downloads import attachment_header
from photo_assistant.api.routes.upload import DeviceOut
from photo_assistant.api.schemas import FiltersIn, Id
from photo_assistant.app.device_sync import RuleSummary
from photo_assistant.app.photo_names import photo_names
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.device_sync import (
    DEFAULT_PAGE,
    MAX_PAGE,
    InvalidSyncRuleError,
    SyncKind,
    SyncMode,
    SyncTarget,
)
from photo_assistant.domain.export_naming import ExportOptions

router = APIRouter(prefix="/api", tags=["device sync"])


# --- schemas ---------------------------------------------------------------------------------


class RuleIn(BaseModel):
    """What to keep on (``include``) or off (``exclude``) the device: the album, the person,
    or the filters (the timeline's query as JSON; search facets go in ``q``)."""

    model_config = ConfigDict(extra="forbid")

    kind: SyncKind
    mode: SyncMode
    album_id: Id | None = None
    person_id: Id | None = None
    filters: FiltersIn | None = None

    def target(self) -> SyncTarget:
        refs = {SyncKind.ALBUM: self.album_id, SyncKind.PERSON: self.person_id}
        if any(ref is not None for kind, ref in refs.items() if kind is not self.kind):
            raise InvalidSyncRuleError(f"a {self.kind} rule names only the {self.kind}")
        filters = None
        if self.filters is not None:
            checked(self.filters.to_filter())
            # one spelling per filter, so the same filters are the same rule
            values = self.filters.model_dump(mode="json", by_alias=True, exclude_defaults=True)
            filters = json.dumps(values, sort_keys=True, separators=(",", ":"))
        return SyncTarget(self.kind, refs.get(self.kind), filters)


class RuleOut(BaseModel):
    id: int
    kind: SyncKind
    mode: SyncMode
    album_id: int | None
    person_id: int | None
    filters: dict[str, object] | None
    label: str | None  # the album's title or the person's name; filters are described by the app
    count: int  # photos it names that you can see
    gone: bool  # it names nothing you can see any more
    view_only: int  # of its photos, those you may only view: they can't go to the phone

    @classmethod
    def of(cls, summary: RuleSummary) -> "RuleOut":
        target = summary.rule.target
        return cls(
            id=summary.rule.id,
            kind=target.kind,
            mode=summary.rule.mode,
            album_id=target.ref_id if target.kind is SyncKind.ALBUM else None,
            person_id=target.ref_id if target.kind is SyncKind.PERSON else None,
            filters=json.loads(target.filters) if target.filters else None,
            label=summary.label,
            count=summary.count,
            gone=summary.gone,
            view_only=summary.view_only,
        )


class SyncSummaryOut(BaseModel):
    device: DeviceOut
    rules: list[RuleOut]
    count: int  # photos on the device's list
    bytes: int
    sent: int  # of them, saved on the phone (it said so)


class ResendOut(BaseModel):
    forgotten: int


class SavedIn(BaseModel):
    ids: list[Id] = Field(min_length=1, max_length=MAX_PAGE)


class SavedOut(BaseModel):
    sent: int


class ManifestItem(BaseModel):
    id: int
    hash: str  # BLAKE3 of the original
    name: str  # the file name it downloads under
    taken_at: datetime
    bytes: int
    mime_type: str | None
    url: str  # where to fetch the original, with the same token


class ManifestOut(BaseModel):
    device: str
    total: int  # photos on the list
    total_bytes: int
    remaining: int  # on the list and not saved on the phone yet
    items: list[ManifestItem]
    next_after: int | None  # pass as ``after`` for the next page; null on the last


# --- the browser: rules ----------------------------------------------------------------------


def _summary(services: ServicesDep, viewer: Viewer, device_id: int) -> SyncSummaryOut:
    s = services.device_sync.summary(viewer, device_id)
    return SyncSummaryOut(
        device=DeviceOut.of(s.device),
        rules=[RuleOut.of(r) for r in s.rules],
        count=s.count,
        bytes=s.bytes,
        sent=s.sent,
    )


@router.get("/devices/{device_id}/sync")
def device_sync_summary(
    device_id: int, user: SessionOnlyUser, services: ServicesDep
) -> SyncSummaryOut:
    return _summary(services, Viewer.of(user), device_id)


@router.post("/devices/{device_id}/sync/rules")
def keep_on_device(
    device_id: int, body: RuleIn, user: SessionOnlyUser, services: ServicesDep
) -> RuleOut:
    viewer = Viewer.of(user)
    rule = services.device_sync.keep(viewer, device_id, body.target(), body.mode)
    rules = services.device_sync.summary(viewer, device_id).rules
    return RuleOut.of(next(r for r in rules if r.rule.id == rule.id))


@router.delete("/devices/{device_id}/sync/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def drop_from_device(
    device_id: int, rule_id: int, user: SessionOnlyUser, services: ServicesDep
) -> Response:
    services.device_sync.drop(Viewer.of(user), device_id, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/devices/{device_id}/sync/resend")
def resend_to_device(device_id: int, user: SessionOnlyUser, services: ServicesDep) -> ResendOut:
    return ResendOut(forgotten=services.device_sync.resend(Viewer.of(user), device_id))


# --- the device: its list and its photos -----------------------------------------------------


@router.get("/sync/manifest")
def manifest(
    caller: DeviceOnly,
    services: ServicesDep,
    new: bool = False,
    after: Id | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> ManifestOut:
    """The photos this device should have, in id order; ``new=true`` only those it has not
    said it saved."""
    viewer = Viewer.of(caller.user)
    page = services.device_sync.manifest(
        viewer, caller.device, new_only=new, after=after, limit=limit
    )
    names = photo_names(services.repo, viewer, page.items)
    entries = services.downloads.plan(page.items, names, ExportOptions())
    return ManifestOut(
        device=caller.device.name,
        total=page.total,
        total_bytes=page.total_bytes,
        remaining=page.remaining,
        items=[
            ManifestItem(
                id=v.id,
                hash=v.asset.content_hash,
                name=entry.name,
                taken_at=v.asset.taken_at,
                bytes=v.asset.byte_size,
                mime_type=v.asset.mime_type,
                url=f"/api/sync/assets/{v.id}/original",
            )
            for v, entry in zip(page.items, entries, strict=True)
        ],
        next_after=page.next_after,
    )


@router.get("/sync/assets/{asset_id}/original")
def original(asset_id: int, caller: DeviceOnly, services: ServicesDep) -> StreamingResponse:
    """The untouched original of a photo on this device's list (404 for any other). Fetching
    marks nothing: the phone says what it saved with ``POST /api/sync/sent``."""
    viewer = Viewer.of(caller.user)
    view = services.device_sync.original(viewer, caller.device, asset_id)
    options = ExportOptions()
    entry = services.downloads.plan([view], photo_names(services.repo, viewer, [view]), options)
    return StreamingResponse(
        services.downloads.content(view, options),
        media_type=view.asset.mime_type or "application/octet-stream",
        headers={"Content-Disposition": attachment_header(entry[0].name)},
    )


@router.post("/sync/sent")
def saved_on_device(body: SavedIn, caller: DeviceOnly, services: ServicesDep) -> SavedOut:
    """The phone saved these photos: ``new=true`` leaves them out from now on. Every id must
    be on this device's list (else ``422`` and nothing is marked); saying it twice is fine."""
    viewer = Viewer.of(caller.user)
    return SavedOut(sent=services.device_sync.saved(viewer, caller.device, body.ids))
