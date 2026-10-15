"""Suggested albums (FEATURES 5.6) for one account: its events, proposed as albums it can keep
or discard. Nothing is made until it keeps one, and an answered suggestion does not come back.

The title comes from facts alone (``domain.events.event_title``). ``Namer`` is the seam for a
later AI rename (an ``AIProvider`` given the event's facts); nothing here calls one.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.errors import NotFoundError
from photo_assistant.domain.events import Event, EventPhoto, album_events, event_title

MAX_SUGGESTIONS = 6  # Home shows a few at a time; answering one brings the next
MOSTLY_IN_ALBUMS = 0.5  # an event with this share of its photos in albums is sorted already
PREVIEW = 4  # photos a suggestion shows besides its cover

type Namer = Callable[[Event], str]


class SuggestionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("this suggestion is no longer there; the list may have changed")


class SuggestionStore(Protocol):
    def event_photos(self, viewer: Viewer) -> list[EventPhoto]: ...
    def photos_in_albums(self, viewer: Viewer) -> set[int]: ...
    def suggestion_answers(self, user_id: int) -> set[str]: ...
    def discard_suggestion(self, user_id: int, key: str, now: datetime) -> bool: ...
    def keep_suggestion(
        self, user_id: int, key: str, title: str, asset_ids: Sequence[int], now: datetime
    ) -> int | None: ...


@dataclass(frozen=True, slots=True)
class Suggestion:
    key: str
    title: str
    first_day: date
    last_day: date
    asset_ids: tuple[int, ...]  # in time order
    cover_id: int  # the middle photo: the first is often the car park

    @property
    def count(self) -> int:
        return len(self.asset_ids)


def _open(store: SuggestionStore, viewer: Viewer, namer: Namer) -> list[Suggestion]:
    """Every suggestion still open for this account, newest first."""
    if viewer.role is Role.GUEST:
        return []  # a guest cannot make an album
    answered = store.suggestion_answers(viewer.user_id)
    in_albums = store.photos_in_albums(viewer)
    found = []
    for event in reversed(album_events(store.event_photos(viewer))):
        ids = tuple(p.asset_id for p in event.photos)
        if event.key in answered or sum(i in in_albums for i in ids) >= MOSTLY_IN_ALBUMS * len(ids):
            continue
        found.append(
            Suggestion(
                event.key, namer(event), event.first_day, event.last_day, ids, ids[len(ids) // 2]
            )
        )
    return found


def suggestions(
    store: SuggestionStore, viewer: Viewer, namer: Namer = event_title
) -> list[Suggestion]:
    return _open(store, viewer, namer)[:MAX_SUGGESTIONS]


def _find(store: SuggestionStore, viewer: Viewer, key: str, namer: Namer) -> Suggestion:
    found = next((s for s in _open(store, viewer, namer) if s.key == key), None)
    if found is None:
        raise SuggestionNotFoundError()
    return found


def keep(
    store: SuggestionStore, viewer: Viewer, key: str, now: datetime, namer: Namer = event_title
) -> int:
    """Make the album (owned by this account, with the photos it sees); its id."""
    found = _find(store, viewer, key, namer)
    album_id = store.keep_suggestion(viewer.user_id, key, found.title, found.asset_ids, now)
    if album_id is None:  # answered meanwhile, from another tab
        raise SuggestionNotFoundError()
    return album_id


def discard(store: SuggestionStore, viewer: Viewer, key: str, now: datetime) -> None:
    _find(store, viewer, key, event_title)
    if not store.discard_suggestion(viewer.user_id, key, now):
        raise SuggestionNotFoundError()
