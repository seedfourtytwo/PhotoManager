"""What "Keep on my phone" (app/device_sync.py) needs from storage and from the library."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.device_sync import SyncMode, SyncRule, SyncTarget
from photo_assistant.ports.library import AssetView


class SyncStore(Protocol):
    def sync_rules(self, device_id: int) -> list[SyncRule]: ...

    def put_sync_rule(
        self, device_id: int, target: SyncTarget, mode: SyncMode, now: datetime
    ) -> SyncRule:
        """Add the rule, or change the mode of the one naming the same thing."""
        ...

    def delete_sync_rule(self, device_id: int, rule_id: int) -> bool: ...

    def sent_ids(self, device_id: int) -> set[int]: ...

    def mark_sent(self, device_id: int, asset_ids: Collection[int], now: datetime) -> None:
        """The phone saved these photos."""
        ...

    def forget_sent(self, device_id: int) -> int:
        """Send everything again: how many photos were marked sent."""
        ...

    def record_sync(self, device_id: int, now: datetime) -> None:
        """The device asked for its list (``device.last_sync_at``)."""
        ...


@dataclass(frozen=True, slots=True)
class Resolved:
    """What a rule's target holds for one viewer."""

    label: str | None  # the album's title, the person's name; None for filters (no name)
    ids: Collection[int]


class SyncScopes(Protocol):
    def resolve(self, viewer: Viewer, target: SyncTarget) -> Resolved | None:
        """The photos the target names that the viewer may see; None when the target names
        nothing they can see (an album deleted or not shared with them, a person gone)."""
        ...


class SyncViews(Protocol):
    def views_by_ids(self, viewer: Viewer, ids: Sequence[int]) -> list[AssetView]:
        """The visibility rule: only live photos the viewer may see, with their level."""
        ...
