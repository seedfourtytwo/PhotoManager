"""Send to a device: make a one-time link for chosen photos, and let one device collect them.

The token in the link is 256 random bits, shown once to the sender; only its SHA-256 is
stored, as for sessions and device tokens (``app/devices.py``). Which photos the sender may
send is the caller's business (the library's visibility rule): this use case is handed the
photo ids and their size, and looks after the link.
"""

import hmac
import secrets
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from photo_assistant.app.devices import hash_token
from photo_assistant.domain.access import Role, User
from photo_assistant.domain.errors import NotFoundError
from photo_assistant.domain.handover import (
    KEPT,
    WRONG_TOKEN_WINDOW,
    Handover,
    HandoverGoneError,
    TooManyTriesError,
    check_cancellable,
    check_size,
    check_transport,
    clean_agent,
    lifetime,
    too_many_wrong_tokens,
    unique_ids,
)
from photo_assistant.ports import Clock
from photo_assistant.ports.handover import HandoverStore, NewHandover

TOKEN_BYTES = 32
LISTED = 200  # the trail shows the newest; older rows stay until they are pruned


class HandoverNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("no such link")


class WrongTokens:
    """Counts tokens that did not work, per client and overall, within the window. Kept in
    memory: a restart forgets them, and a token cannot be guessed in the first place."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._tries: deque[tuple[datetime, str]] = deque()
        self._guard = threading.Lock()

    def _recent(self) -> deque[tuple[datetime, str]]:
        since = self._clock.now() - WRONG_TOKEN_WINDOW
        while self._tries and self._tries[0][0] <= since:
            self._tries.popleft()
        return self._tries

    def blocked(self, client: str) -> bool:
        with self._guard:
            recent = self._recent()
            return too_many_wrong_tokens(sum(c == client for _, c in recent), len(recent))

    def record(self, client: str) -> None:
        with self._guard:
            self._recent().append((self._clock.now(), client))


@dataclass(frozen=True, slots=True)
class HandoverRules:
    """What the admin set (docs/guides/settings.md)."""

    minutes: int
    unencrypted_allowed: bool


class Handovers:
    def __init__(self, store: HandoverStore, clock: Clock, rules: HandoverRules) -> None:
        self._store = store
        self._clock = clock
        self._rules = rules
        self._life = lifetime(rules.minutes)  # a setting out of range stops the start
        self._wrong = WrongTokens(clock)

    # --- the sender -------------------------------------------------------------------------

    def check(self, count: int, byte_size: int, *, encrypted: bool, confirmed: bool) -> None:
        """Everything that can refuse a new link, before anything is stored."""
        check_size(count, byte_size)
        check_transport(
            encrypted=encrypted,
            unencrypted_allowed=self._rules.unencrypted_allowed,
            confirmed=confirmed,
        )

    def create(
        self,
        user: User,
        asset_ids: list[int],
        byte_size: int,
        *,
        encrypted: bool,
        details_removed: bool,
        confirmed_unencrypted: bool = False,
    ) -> tuple[Handover, str]:
        """The new hand-over and its token (the only time the token is ever available)."""
        ids = unique_ids(asset_ids)
        self.check(len(ids), byte_size, encrypted=encrypted, confirmed=confirmed_unencrypted)
        token = secrets.token_urlsafe(TOKEN_BYTES)
        now = self._clock.now()
        handover = self._store.add_handover(
            NewHandover(
                token_hash=hash_token(token),
                created_by=user.id,
                created_at=now,
                expires_at=now + self._life,
                asset_ids=ids,
                byte_size=byte_size,
                encrypted=encrypted,
                details_removed=details_removed,
            )
        )
        return handover, token

    def get_for(self, user: User, handover_id: int) -> Handover:
        """One's own hand-over, or anyone's for an admin; otherwise it is not there."""
        handover = self._store.get_handover(handover_id)
        if handover is None or not _may_manage(user, handover):
            raise HandoverNotFoundError()
        return handover

    def list_for(self, user: User) -> list[Handover]:
        """The trail: an admin reads everyone's, a member their own. Newest first."""
        created_by = None if user.role is Role.ADMIN else user.id
        return self._store.list_handovers(created_by, LISTED)

    def cancel(self, user: User, handover_id: int) -> None:
        handover = self.get_for(user, handover_id)
        now = self._clock.now()
        check_cancellable(handover, now)
        if not self._store.cancel_handover(handover.id, now):
            # collected or run out between the check and the write: say what it is now
            check_cancellable(self.get_for(user, handover_id), self._clock.now())

    # --- the receiving device ---------------------------------------------------------------

    def find(self, token: str, client: str) -> Handover:
        """The waiting hand-over this token opens. Anything else (wrong, used, run out,
        cancelled) is one answer, and is counted against ``client``."""
        if self._wrong.blocked(client):
            raise TooManyTriesError()
        presented = hash_token(token)
        found = self._store.handover_by_token_hash(presented)
        if (
            found is None
            or not hmac.compare_digest(found[1], presented)
            or not found[0].collectable(self._clock.now())
        ):
            self._wrong.record(client)
            raise HandoverGoneError()
        return found[0]

    def collect(self, handover: Handover, client: str, agent: str | None) -> None:
        """Use the link up. Atomic: of two devices at the same moment, one gets through."""
        won = self._store.redeem_handover(
            handover.id, self._clock.now(), client, clean_agent(agent)
        )
        if not won:
            raise HandoverGoneError()

    def burn(self, handover: Handover) -> None:
        """Its token was seen where it should never travel (plain http for an https link):
        nobody collects it any more."""
        self._store.cancel_handover(handover.id, self._clock.now())

    # --- housekeeping -----------------------------------------------------------------------

    def prune(self) -> int:
        return self._store.prune_handovers(self._clock.now() - KEPT)


def _may_manage(user: User, handover: Handover) -> bool:
    return user.role is Role.ADMIN or handover.created_by == user.id
