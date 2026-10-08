"""Review (issue 8): hold doubtful photos out of the library; a person keeps or discards them.

A held photo is already copied into the library folder, so deciding never needs its source
again. Keeping it makes it an ordinary photo; discarding it moves it to the 30-day trash.
Either way it is never held a second time.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.grouping import Shot
from photo_assistant.domain.review import LOOKALIKE, clutter_reason, lookalikes
from photo_assistant.domain.tags import TagScore
from photo_assistant.ports import Clock
from photo_assistant.ports.library import AssetView


class ReviewStore(Protocol):
    def shots(self) -> list[Shot]:
        """Every photo in the library (not trashed, not held), with its time and hash."""
        ...

    def hold_asset(self, asset_id: int, reason: str, like: int | None) -> bool:
        """Hold a library photo nobody has decided about yet; False when it was left alone."""
        ...

    def held_views(self, viewer: Viewer) -> list[AssetView]: ...
    def count_held(self, viewer: Viewer) -> int: ...
    def release_assets(self, ids: Sequence[int], now: datetime) -> int: ...
    def discard_held(self, ids: Sequence[int], user_id: int, now: datetime) -> int:
        """Held photos among ``ids`` go to the trash, in one step."""
        ...


class Review:
    def __init__(self, store: ReviewStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def hold_lookalikes(self, new: set[int]) -> int:
        """Hold the just-imported photos that look like one already in the library."""
        shots = self._store.shots()
        fresh = [s for s in shots if s.asset_id in new]
        found = lookalikes(fresh, [s for s in shots if s.asset_id not in new])
        return sum(self._store.hold_asset(i, LOOKALIKE, like) for i, like in found.items())

    def hold_clutter(self, asset_id: int, tags: Sequence[TagScore]) -> bool:
        reason = clutter_reason(tags)
        return reason is not None and self._store.hold_asset(asset_id, reason, None)

    def waiting(self, viewer: Viewer) -> list[AssetView]:
        return self._store.held_views(viewer)

    def count(self, viewer: Viewer) -> int:
        return self._store.count_held(viewer)

    def keep(self, ids: Sequence[int]) -> int:
        return self._store.release_assets(ids, self._clock.now())

    def discard(self, ids: Sequence[int], user_id: int) -> int:
        return self._store.discard_held(ids, user_id, self._clock.now())
