"""Memories on Home (issue 54): the library's trips, found from capture times alone.

A trip is a run of photos where each follows the one before within two days; a run of fewer
than ten is a day out, not a memory. A memory is named after its main place and its months
("Lisbon, July and August 2024"). Home shows the two newest, then a few others that change
every day, so it reads differently each morning while staying the same all day.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MAX_GAP = timedelta(days=2)  # a trip goes on while photos are at most this far apart
MIN_PHOTOS = 10  # fewer than this is a day out, not a memory
MAX_MEMORIES = 8
NEWEST_FIRST = 2  # always first; the rest take turns, a page a day

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True, slots=True)
class Moment:
    """One photo as Home sees it."""

    asset_id: int
    taken_at: datetime  # local wall-clock
    place: str | None  # the name of its city (or region, or country), if it has a place
    favourite: bool = False  # the viewer's own


@dataclass(frozen=True, slots=True)
class Memory:
    key: str  # stable while the trip stays as it is: its first and last day
    title: str
    first_day: date
    last_day: date
    count: int
    cover_id: int


def _by_time(moments: Sequence[Moment]) -> list[Moment]:
    return sorted(moments, key=lambda m: (m.taken_at, m.asset_id))


def trips(moments: Sequence[Moment]) -> list[list[Moment]]:
    """Every trip in the library, oldest first, each in time order."""
    found: list[list[Moment]] = []
    run: list[Moment] = []
    for moment in _by_time(moments):
        if run and moment.taken_at - run[-1].taken_at > MAX_GAP:
            found.append(run)
            run = []
        run.append(moment)
    found.append(run)
    return [t for t in found if len(t) >= MIN_PHOTOS]


def dominant_place(moments: Sequence[Moment]) -> str | None:
    """The place most of the photos with one were taken at; a tie goes to the first seen."""
    places = Counter(m.place for m in _by_time(moments) if m.place)
    # most_common keeps first-seen order among equal counts
    return places.most_common(1)[0][0] if places else None


def period_words(first: date, last: date) -> str:
    """ "July 2024", "July and August 2024", "July to September 2024", across years
    "December 2023 and January 2024"."""
    start, end = (first.year, first.month), (last.year, last.month)
    months = (end[0] - start[0]) * 12 + end[1] - start[1]
    joiner = " and " if months == 1 else " to "
    if months == 0:
        return f"{MONTHS[last.month - 1]} {last.year}"
    if first.year == last.year:
        return f"{MONTHS[first.month - 1]}{joiner}{MONTHS[last.month - 1]} {last.year}"
    return f"{MONTHS[first.month - 1]} {first.year}{joiner}{MONTHS[last.month - 1]} {last.year}"


def trip_title(trip: Sequence[Moment]) -> str:
    ordered = _by_time(trip)
    period = period_words(ordered[0].taken_at.date(), ordered[-1].taken_at.date())
    place = dominant_place(ordered)
    return f"{place}, {period}" if place else period


def cover_of(moments: Sequence[Moment]) -> int:
    """The first favourite, else the first photo (by time)."""
    ordered = _by_time(moments)
    return next((m for m in ordered if m.favourite), ordered[0]).asset_id


def memory_of(trip: Sequence[Moment]) -> Memory:
    ordered = _by_time(trip)
    first, last = ordered[0].taken_at.date(), ordered[-1].taken_at.date()
    return Memory(
        key=f"{first.isoformat()}_{last.isoformat()}",
        title=trip_title(ordered),
        first_day=first,
        last_day=last,
        count=len(ordered),
        cover_id=cover_of(ordered),
    )


def _turn(items: list[Memory], today: date, size: int) -> list[Memory]:
    """``size`` of ``items``, a different page each day. When they all fit, their order turns
    instead, so Home still changes from one day to the next."""
    n = len(items)
    if n == 0:
        return []
    step = size if n > size else 1
    start = (today.toordinal() * step) % n
    return [items[(start + i) % n] for i in range(min(size, n))]


def memories(moments: Sequence[Moment], today: date) -> list[Memory]:
    """What Home lists: the two newest trips, then the others' page for ``today``."""
    newest_first = [memory_of(t) for t in reversed(trips(moments))]
    head, rest = newest_first[:NEWEST_FIRST], newest_first[NEWEST_FIRST:]
    return head + _turn(rest, today, MAX_MEMORIES - NEWEST_FIRST)
