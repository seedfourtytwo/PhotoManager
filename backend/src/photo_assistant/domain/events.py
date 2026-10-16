"""Events (FEATURES 5.6): the library split into trips, birthdays and days out, to propose as
albums, without AI.

One pass in time order decides, between each photo and the event so far, whether it goes on:
1. Moved: more than ``MOVED_KM`` from the event's last known position ends the event, unless
   both are away from home (a day out with two stops, a road trip).
2. Close in time: at most ``SAME_EVENT_GAP`` after the last photo goes on.
3. A night on a trip: both away from home and at most ``OVERNIGHT_GAP`` apart goes on, so a
   trip crosses midnight. At home a night always splits (every day at home is its own event).
4. The same people: at most ``SAME_PEOPLE_GAP`` later with a person already in the event goes
   on (lunch, then the cake at four). This only breaks the tie the time gap leaves.
Home is the place with the most photos (a grid cell of ``HOME_CELL_DEG``); "away" is more than
``AWAY_KM`` from it. Without any GPS there is no home, so nothing is away.
A photo without a real date belongs to no event; one without GPS takes the event's last known
position. An event with ``MIN_PHOTOS`` is worth an album.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import asin, cos, floor, radians, sin, sqrt

from photo_assistant.domain.memories import MONTHS, period_words
from photo_assistant.domain.places import Place

SAME_EVENT_GAP = timedelta(hours=3)
SAME_PEOPLE_GAP = timedelta(hours=6)
OVERNIGHT_GAP = timedelta(hours=16)
MOVED_KM = 25.0
AWAY_KM = 30.0
HOME_CELL_DEG = 0.1  # about 11 km of latitude
MIN_PHOTOS = 8
EARTH_RADIUS_KM = 6371.0

type LatLon = tuple[float, float]


@dataclass(frozen=True, slots=True)
class EventPhoto:
    asset_id: int
    taken_at: datetime | None  # local wall-clock; None: no real date
    position: LatLon | None  # GPS
    people: frozenset[int] = frozenset()  # person ids of the faces on it
    place: Place | None = None  # its name, when the geocoder gave one


@dataclass(frozen=True, slots=True)
class Event:
    photos: tuple[EventPhoto, ...]  # in time order, every one dated

    @property
    def key(self) -> str:
        """Stable while the event grows: its oldest photo in the library (the smallest id)."""
        return str(min(p.asset_id for p in self.photos))

    @property
    def first_day(self) -> date:
        return _at(self.photos[0]).date()

    @property
    def last_day(self) -> date:
        return _at(self.photos[-1]).date()

    @property
    def count(self) -> int:
        return len(self.photos)


def _at(p: EventPhoto) -> datetime:
    assert p.taken_at is not None  # an event holds dated photos only
    return p.taken_at


def distance_km(a: LatLon, b: LatLon) -> float:
    """Great-circle distance (haversine)."""
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def _home(ordered: Sequence[EventPhoto]) -> LatLon | None:
    """The middle of the grid cell holding the most photos (a tie: the one seen first)."""
    cells: dict[tuple[int, int], list[LatLon]] = {}
    for p in ordered:
        if p.position is not None:
            lat, lon = p.position
            cells.setdefault((floor(lat / HOME_CELL_DEG), floor(lon / HOME_CELL_DEG)), []).append(
                p.position
            )
    if not cells:
        return None
    most = max(cells.values(), key=len)  # max keeps the first of equals
    return (sum(x for x, _ in most) / len(most), sum(y for _, y in most) / len(most))


class _Run:
    """The event being built."""

    def __init__(self, first: EventPhoto) -> None:
        self.photos = [first]
        self.position = first.position
        self.people = set(first.people)

    def add(self, p: EventPhoto) -> None:
        self.photos.append(p)
        self.position = p.position or self.position
        self.people |= p.people


def _goes_on(run: _Run, p: EventPhoto, home: LatLon | None) -> bool:
    def away(where: LatLon | None) -> bool:
        return where is not None and home is not None and distance_km(home, where) > AWAY_KM

    travelling = away(run.position) and away(p.position)
    if (
        run.position is not None
        and p.position is not None
        and not travelling
        and distance_km(run.position, p.position) > MOVED_KM
    ):
        return False
    gap = _at(p) - _at(run.photos[-1])
    return (
        gap <= SAME_EVENT_GAP
        or (travelling and gap <= OVERNIGHT_GAP)
        or (gap <= SAME_PEOPLE_GAP and not run.people.isdisjoint(p.people))
    )


def split_events(photos: Sequence[EventPhoto]) -> list[Event]:
    """Every event, oldest first; photos without a real date are left out."""
    ordered = sorted(
        (p for p in photos if p.taken_at is not None), key=lambda p: (_at(p), p.asset_id)
    )
    home = _home(ordered)
    runs: list[_Run] = []
    for p in ordered:
        if runs and _goes_on(runs[-1], p, home):
            runs[-1].add(p)
        else:
            runs.append(_Run(p))
    return [Event(tuple(r.photos)) for r in runs]


def album_events(photos: Sequence[EventPhoto]) -> list[Event]:
    """The events big enough to be worth an album, oldest first."""
    return [e for e in split_events(photos) if e.count >= MIN_PHOTOS]


def _place_name(event: Event) -> str | None:
    """The one city all its named photos share, else the one region, else the one country,
    else the city with the most of them (a tie: the first seen)."""
    places = [p.place for p in event.photos if p.place is not None]
    for names in (
        {place.city for place in places},
        {place.region for place in places},
        {place.country for place in places},
    ):
        if len(names) == 1 and "" not in names:
            return names.pop()
    cities = Counter(place.city or place.region or place.country for place in places)
    return cities.most_common(1)[0][0] if cities else None


def event_title(event: Event) -> str:
    """A plain title from facts alone: "Brittany · July 2025", "Rennes · 8 March 2025"."""
    first, last = event.first_day, event.last_day
    when = (
        f"{first.day} {MONTHS[first.month - 1]} {first.year}"
        if first == last
        else period_words(first, last)
    )
    place = _place_name(event)
    return f"{place} · {when}" if place else when
