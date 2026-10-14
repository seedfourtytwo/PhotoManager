"""Keep on my phone (FEATURES 10.6): the list one device should hold, and serving it.

Each of a person's devices has its own rules (albums, people, filters; kept or left off). The
list is computed on every request, never stored: it follows the library (a photo added to a
kept album, a photo trashed, an album unshared) without any bookkeeping. Only what the device
already fetched is stored, so it can ask for "only new".

Access: a rule's photos come narrowed to what the owner may see; on top of that the list keeps
only photos they may *download* (a sync is a download) and have not hidden. A device fetches
only photos on its own list, whatever else its owner may see.
"""

from dataclasses import dataclass

from photo_assistant.domain.access import Level, Viewer
from photo_assistant.domain.device_sync import (
    MAX_RULES,
    InvalidSyncRuleError,
    SyncMode,
    SyncRule,
    SyncTarget,
    kept_ids,
    manifest_page,
)
from photo_assistant.domain.errors import NotFoundError
from photo_assistant.ports import Clock
from photo_assistant.ports.device_sync import SyncScopes, SyncStore, SyncViews
from photo_assistant.ports.library import AssetView
from photo_assistant.ports.upload import Device, DeviceStore


class DeviceNotFoundError(NotFoundError):
    """Not one of the caller's active devices."""


class SyncRuleNotFoundError(NotFoundError):
    pass


class SyncTargetNotFoundError(NotFoundError):
    """The album or person to keep is not one the caller can see."""


class SyncPhotoNotFoundError(NotFoundError):
    """The photo is not on this device's list."""


@dataclass(frozen=True, slots=True)
class RuleSummary:
    rule: SyncRule
    label: str | None  # the album's title or the person's name
    count: int  # photos the rule names that the owner can see
    gone: bool  # it names nothing the owner can see any more (unshared, merged away)


@dataclass(frozen=True, slots=True)
class SyncSummary:
    device: Device
    rules: list[RuleSummary]
    count: int  # photos on the list
    bytes: int
    sent: int  # of them, already fetched by the device


@dataclass(frozen=True, slots=True)
class ManifestPage:
    items: list[AssetView]
    total: int  # the whole list
    total_bytes: int
    remaining: int  # on the list and not fetched yet
    next_after: int | None


class DeviceSync:
    def __init__(
        self,
        devices: DeviceStore,
        store: SyncStore,
        scopes: SyncScopes,
        views: SyncViews,
        clock: Clock,
    ) -> None:
        self._devices = devices
        self._store = store
        self._scopes = scopes
        self._views = views
        self._clock = clock

    def device(self, viewer: Viewer, device_id: int) -> Device:
        """One of the viewer's own devices that still works."""
        found = next(
            (d for d in self._devices.list_devices(viewer.user_id) if d.id == device_id), None
        )
        if found is None or found.revoked_at is not None:
            raise DeviceNotFoundError("device not found")
        return found

    # --- rules (a signed-in browser) -----------------------------------------------------------

    def keep(self, viewer: Viewer, device_id: int, target: SyncTarget, mode: SyncMode) -> SyncRule:
        """Keep ``target`` on the device (include) or off it (exclude); naming the same thing
        again changes its mode."""
        self.device(viewer, device_id)
        target.check()
        if self._scopes.resolve(viewer, target) is None:
            raise SyncTargetNotFoundError(f"no {target.kind} like that to keep")
        rules = self._store.sync_rules(device_id)
        if len(rules) >= MAX_RULES and all(r.target != target for r in rules):
            raise InvalidSyncRuleError(
                f"a device keeps at most {MAX_RULES} albums, people and filters"
            )
        return self._store.put_sync_rule(device_id, target, mode, self._clock.now())

    def drop(self, viewer: Viewer, device_id: int, rule_id: int) -> None:
        self.device(viewer, device_id)
        if not self._store.delete_sync_rule(device_id, rule_id):
            raise SyncRuleNotFoundError("that album, person or filter is not on this device")

    def resend(self, viewer: Viewer, device_id: int) -> int:
        """Offer every photo of the list again, as "new" (after a phone was reset)."""
        self.device(viewer, device_id)
        return self._store.forget_sent(device_id)

    def summary(self, viewer: Viewer, device_id: int) -> SyncSummary:
        device = self.device(viewer, device_id)
        rules, kept = self._list(viewer, device_id)
        sent = self._store.sent_ids(device_id)
        return SyncSummary(
            device=device,
            rules=rules,
            count=len(kept),
            bytes=sum(v.asset.byte_size for v in kept),
            sent=sum(1 for v in kept if v.id in sent),
        )

    # --- the device itself (its token) ---------------------------------------------------------

    def manifest(
        self, viewer: Viewer, device: Device, *, new_only: bool, after: int | None, limit: int
    ) -> ManifestPage:
        """One page of the device's list in id order; ``new_only`` leaves out what it has
        fetched before."""
        _, kept = self._list(viewer, device.id)
        sent = self._store.sent_ids(device.id)
        wanted = [v for v in kept if not (new_only and v.id in sent)]
        by_id = {v.id: v for v in wanted}
        page, next_after = manifest_page(list(by_id), after=after, limit=limit)
        self._store.record_sync(device.id, self._clock.now())
        return ManifestPage(
            items=[by_id[i] for i in page],
            total=len(kept),
            total_bytes=sum(v.asset.byte_size for v in kept),
            remaining=sum(1 for v in kept if v.id not in sent),
            next_after=next_after,
        )

    def original(self, viewer: Viewer, device: Device, asset_id: int) -> AssetView:
        """The photo, if it is on the device's list."""
        _, kept = self._list(viewer, device.id)
        found = next((v for v in kept if v.id == asset_id), None)
        if found is None:
            raise SyncPhotoNotFoundError("photo not found")
        return found

    def sent(self, device: Device, asset_id: int) -> None:
        """The device received the whole file."""
        self._store.mark_sent(device.id, asset_id, self._clock.now())

    # --- the list ------------------------------------------------------------------------------

    def _list(self, viewer: Viewer, device_id: int) -> tuple[list[RuleSummary], list[AssetView]]:
        """Each rule as the viewer sees it, and the list: photos they may download and have
        not hidden, in id order."""
        summaries: list[RuleSummary] = []
        includes: list[list[int]] = []
        excludes: list[list[int]] = []
        for rule in self._store.sync_rules(device_id):
            resolved = self._scopes.resolve(viewer, rule.target)
            ids = list(resolved.ids) if resolved else []
            label = resolved.label if resolved else None
            summaries.append(RuleSummary(rule, label, len(ids), resolved is None))
            (includes if rule.mode is SyncMode.INCLUDE else excludes).append(ids)
        views = self._views.views_by_ids(viewer, kept_ids(includes, excludes))
        kept = [v for v in views if v.level >= Level.DOWNLOAD and not v.hidden]
        return summaries, sorted(kept, key=lambda v: v.id)
