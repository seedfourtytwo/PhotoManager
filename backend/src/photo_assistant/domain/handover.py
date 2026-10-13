"""Send to a device: the pure rules of a hand-over (spec 2026-10-13).

A hand-over is a fixed list of photos that one device may collect once, within minutes, with
a link instead of an account. What state it is in is worked out here from what was recorded
(when it runs out, how often it was collected, whether it was cancelled), never stored.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from photo_assistant.domain.errors import ConflictError, DomainError, ForbiddenError, InvalidError
from photo_assistant.domain.export_naming import ExportOptions

DEFAULT_MINUTES = 10
MIN_MINUTES, MAX_MINUTES = 1, 60
MAX_PHOTOS = 100
MAX_BYTES = 1_000_000_000  # of the copies that are sent, as Download estimates them
# Wrong tokens within the window, before more tries are refused: the PIN limit's idea. A token
# is 256 random bits, so this only keeps a guesser from keeping the server busy.
MAX_WRONG_TOKENS_PER_CLIENT = 10
MAX_WRONG_TOKENS_OVERALL = 100
WRONG_TOKEN_WINDOW = timedelta(minutes=15)
KEPT = timedelta(days=90)  # the trail: who sent how many photos, when, collected or not
NEUTRAL_NAME = "photo"  # a file's name when details are removed (dates and devices hide there)
MAX_AGENT_CHARS = 200
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class HandoverState(StrEnum):
    WAITING = "waiting"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class HandoverGoneError(DomainError):
    """THE answer to a token that does not work: wrong, used, run out or cancelled all read
    the same, so nobody can tell which by trying."""

    status = 404

    def __init__(self) -> None:
        super().__init__(
            "this link does not work any more: it was used, ran out or was cancelled; "
            "ask for a new one"
        )


class TooManyTriesError(DomainError):
    status = 429

    def __init__(self) -> None:
        super().__init__("too many links that do not work were tried; wait 15 minutes")


class HandoverTooLargeError(InvalidError):
    """More photos or bytes than one hand-over takes, or none at all."""


class InvalidLifetimeError(InvalidError):
    def __init__(self) -> None:
        super().__init__(f"a link lasts {MIN_MINUTES} to {MAX_MINUTES} minutes")


class NotCancellableError(ConflictError):
    """Only a hand-over that still waits can be cancelled."""


class UnencryptedNotConfirmedError(ConflictError):
    def __init__(self) -> None:
        super().__init__(
            "this link is not encrypted: anyone on the same network could see the photos "
            "while they travel; confirm to send anyway"
        )


class UnencryptedNotAllowedError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            "sending without encryption is switched off here: open the library at its "
            "https address and send from there"
        )


@dataclass(frozen=True, slots=True)
class Handover:
    id: int
    created_by: int
    created_at: datetime
    expires_at: datetime
    asset_ids: tuple[int, ...]
    byte_size: int
    encrypted: bool  # the link is an https one
    details_removed: bool  # the copies carry no metadata and no original file names
    max_redemptions: int = 1
    redemptions: int = 0
    redeemed_at: datetime | None = None
    redeemed_from: str | None = None  # the address that collected it
    redeemed_agent: str | None = None  # what its browser called itself
    cancelled_at: datetime | None = None

    def state(self, now: datetime) -> HandoverState:
        if self.cancelled_at is not None:
            return HandoverState.CANCELLED
        if self.redemptions >= self.max_redemptions:
            return HandoverState.REDEEMED
        if now >= self.expires_at:  # at the very moment it runs out, it is over
            return HandoverState.REDEEMED if self.redemptions else HandoverState.EXPIRED
        return HandoverState.WAITING

    def collectable(self, now: datetime) -> bool:
        return self.state(now) is HandoverState.WAITING


def lifetime(minutes: int) -> timedelta:
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise InvalidLifetimeError()
    return timedelta(minutes=minutes)


def unique_ids(ids: Iterable[int]) -> tuple[int, ...]:
    """Each photo once, in the order given."""
    return tuple(dict.fromkeys(ids))


def check_size(count: int, byte_size: int) -> None:
    if count < 1:
        raise HandoverTooLargeError("choose at least one photo to send")
    if count > MAX_PHOTOS:
        raise HandoverTooLargeError(
            f"a link carries at most {MAX_PHOTOS} photos; you chose {count}"
        )
    if byte_size > MAX_BYTES:
        raise HandoverTooLargeError(
            f"these photos are too big for one link (about {MAX_BYTES // 10**9} GB at most); "
            "send fewer at a time"
        )


def check_cancellable(handover: Handover, now: datetime) -> None:
    state = handover.state(now)
    if state is HandoverState.WAITING:
        return
    why = {
        HandoverState.REDEEMED: "these photos were already downloaded",
        HandoverState.EXPIRED: "this link has already run out",
        HandoverState.CANCELLED: "this link was already cancelled",
    }[state]
    raise NotCancellableError(why)


def export_options(*, details_removed: bool) -> ExportOptions:
    """The copy that is sent: a full-size JPEG with the edits, which any phone opens (the
    Download dialog's "With edits"). With details removed it carries no metadata at all;
    the renderer keeps it upright and keeps its colour profile."""
    return ExportOptions(format="jpeg", strip_all_metadata=details_removed)


def file_names(original_names: Sequence[str], *, details_removed: bool) -> list[str]:
    """What each photo is called on the way out: its own name, or a neutral one."""
    if details_removed:
        return [NEUTRAL_NAME] * len(original_names)
    return list(original_names)


def check_transport(*, encrypted: bool, unencrypted_allowed: bool, confirmed: bool) -> None:
    """A link that is not https needs the admin's switch and the sender's yes, every time."""
    if encrypted:
        return
    if not unencrypted_allowed:
        raise UnencryptedNotAllowedError()
    if not confirmed:
        raise UnencryptedNotConfirmedError()


def may_travel(handover: Handover, *, arrived_encrypted: bool) -> bool:
    """A link made as an https one is never honoured over plain http: the sender was told
    it was encrypted. One made unencrypted, with the warning, may arrive either way."""
    return arrived_encrypted or not handover.encrypted


def too_many_wrong_tokens(from_this_client: int, overall: int) -> bool:
    return from_this_client >= MAX_WRONG_TOKENS_PER_CLIENT or overall >= MAX_WRONG_TOKENS_OVERALL


def clean_agent(agent: str | None) -> str | None:
    """A browser's own description, for the trail: printable and short, or nothing."""
    text = _CONTROL.sub("", agent or "").strip()[:MAX_AGENT_CHARS]
    return text or None
