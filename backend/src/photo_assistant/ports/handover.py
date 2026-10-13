"""Port for the hand-overs of "send to a device" (domain/handover.py has the rules)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from photo_assistant.domain.handover import Handover


@dataclass(frozen=True, slots=True)
class NewHandover:
    token_hash: str
    created_by: int
    created_at: datetime
    expires_at: datetime
    asset_ids: Sequence[int]
    byte_size: int
    encrypted: bool
    details_removed: bool
    max_redemptions: int = 1


class HandoverStore(Protocol):
    def add_handover(self, new: NewHandover) -> Handover: ...

    def handover_by_token_hash(self, token_hash: str) -> tuple[Handover, str] | None:
        """The hand-over and the hash as stored, for the caller to compare in constant time."""
        ...

    def get_handover(self, handover_id: int) -> Handover | None: ...

    def list_handovers(self, created_by: int | None, limit: int) -> list[Handover]:
        """Newest first; ``created_by`` None = everyone's."""
        ...

    def redeem_handover(
        self, handover_id: int, now: datetime, client: str, agent: str | None
    ) -> bool:
        """Count one collection if it still waits at ``now``. One atomic step: of two calls
        at the same moment for a single-use hand-over, exactly one gets True."""
        ...

    def cancel_handover(self, handover_id: int, now: datetime) -> bool:
        """Cancel it if it still waits at ``now``; False if it no longer did."""
        ...

    def prune_handovers(self, before: datetime) -> int:
        """Delete the hand-overs made before then; returns how many."""
        ...
