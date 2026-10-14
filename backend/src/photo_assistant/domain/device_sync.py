"""Keep on my phone (FEATURES 10.6): which photos one device should hold.

A device has rules. Each names an album, a person or a filter (the timeline's filters, search
words and facets included) and either keeps it on the device (include) or leaves it off
(exclude). The device's list is every photo some include names, minus every photo some exclude
names, each photo once (a photo is one asset whatever its copies, so there is nothing to merge).

Who may see what is not decided here: each rule's photos come already narrowed by the
repository's visibility rule (ARCHITECTURE §7) for the device's owner.

The sync is one way, server to phone: what is deleted on the phone is not deleted here.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from photo_assistant.domain.errors import InvalidError

MAX_RULES = 50  # per device: a list a person can still read on the Devices page
DEFAULT_PAGE = 50  # small pages for Apple Shortcuts, which holds a whole answer in memory
MAX_PAGE = 200


class InvalidSyncRuleError(InvalidError):
    """A rule or a manifest request that cannot be taken as asked."""


class SyncKind(StrEnum):
    ALBUM = "album"
    PERSON = "person"
    FILTER = "filter"


class SyncMode(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


@dataclass(frozen=True, slots=True)
class SyncTarget:
    """What a rule names: an album or a person by id, or filters as canonical JSON."""

    kind: SyncKind
    ref_id: int | None = None
    filters: str | None = None

    def check(self) -> None:
        if self.kind is SyncKind.FILTER:
            if self.filters is None:
                raise InvalidSyncRuleError("a filter rule needs the filters")
            if self.ref_id is not None:
                raise InvalidSyncRuleError("a filter rule names no album or person")
            return
        if self.ref_id is None:
            raise InvalidSyncRuleError(f"{_article(self.kind)} rule needs the {self.kind}")
        if self.filters is not None:
            raise InvalidSyncRuleError(f"{_article(self.kind)} rule names only the {self.kind}")


def _article(kind: SyncKind) -> str:
    return f"an {kind}" if kind is SyncKind.ALBUM else f"a {kind}"


@dataclass(frozen=True, slots=True)
class SyncRule:
    id: int
    target: SyncTarget
    mode: SyncMode


def kept_ids(includes: Iterable[Iterable[int]], excludes: Iterable[Iterable[int]]) -> list[int]:
    """The device's list: the union of the includes minus the union of the excludes, by id."""
    kept = {i for photos in includes for i in photos}
    for photos in excludes:
        kept.difference_update(photos)
    return sorted(kept)


def manifest_page(
    ids: Sequence[int], *, after: int | None, limit: int
) -> tuple[list[int], int | None]:
    """One page of a sorted id list after ``after``, and the ``after`` of the next page (None
    on the last). Paging by id, not by position, so a photo joining or leaving the list
    between two requests moves nothing else."""
    if not 1 <= limit <= MAX_PAGE:
        raise InvalidSyncRuleError(f"ask for 1 to {MAX_PAGE} photos at a time")
    rest = [i for i in ids if after is None or i > after]
    page = rest[:limit]
    return page, (page[-1] if len(rest) > limit else None)
