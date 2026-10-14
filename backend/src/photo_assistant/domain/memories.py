"""Memories on Home (issue 54): trips away from home and months at home, from capture times
and places alone.

Home is the city with the most photos. A trip is a run of photos away from it in one city,
each within two days of the one before, 21 days at most and ten photos at least ("Lisbon, July
and August 2024"). A calendar month with twenty photos at home is a memory too ("October
2024"): a family that takes photos every day would otherwise have one endless "trip". Home
shows the two newest, then a few others that change every day, so it reads differently each
morning while staying the same all day.
"""

from calendar import monthrange
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from operator import attrgetter
from typing import NamedTuple

MAX_GAP = timedelta(days=2)  # a trip goes on while photos are at most this far apart
MAX_TRIP = timedelta(days=21)  # a longer stay away is several trips
MIN_PHOTOS = 10  # fewer than this is a day out, not a memory
MIN_AT_HOME = 20  # photos at home in a calendar month that make it a memory
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


class Moment(NamedTuple):
    """One photo as Home sees it. A named tuple, not a dataclass: Home builds one for every
    photo of the library on each visit, and a tuple is made in half the time."""

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


_BY_TIME = attrgetter("taken_at", "asset_id")


def by_time(moments: Iterable[Moment]) -> list[Moment]:
    return sorted(moments, key=_BY_TIME)


def home_place(moments: Sequence[Moment]) -> str | None:
    """The city with the most photos (a tie: the one seen first); None when none has a place."""
    return dominant_place(moments)


def _away_places(ordered: Sequence[Moment], home: str | None) -> list[str | None]:
    """Where each photo (in time order) was taken when away; None at home. A photo without a
    place goes with the nearest photo that has one, within two days; when two places are as
    near, or none is, it counts as home."""
    n = len(ordered)
    before: list[int | None] = [None] * n
    after: list[int | None] = [None] * n
    last: int | None = None
    for i, m in enumerate(ordered):
        before[i] = last
        if m.place:
            last = i
    last = None
    for i in range(n - 1, -1, -1):
        after[i] = last
        if ordered[i].place:
            last = i
    places: list[str | None] = []
    for i, m in enumerate(ordered):
        place = m.place or _nearest_place(ordered, i, before[i], after[i])
        places.append(None if place == home else place)
    return places


def _nearest_place(
    ordered: Sequence[Moment], i: int, before: int | None, after: int | None
) -> str | None:
    at = ordered[i].taken_at
    gaps = [(at - ordered[before].taken_at, before)] if before is not None else []
    gaps += [(ordered[after].taken_at - at, after)] if after is not None else []
    near = sorted(g for g in gaps if g[0] <= MAX_GAP)
    if not near:
        return None
    place = ordered[near[0][1]].place
    as_near = [ordered[j].place for gap, j in near if gap == near[0][0]]
    return place if all(p == place for p in as_near) else None  # two places as near: unclear


def _trips(
    ordered: Sequence[Moment], places: Sequence[str | None]
) -> list[tuple[str, list[Moment]]]:
    found: list[tuple[str, list[Moment]]] = []
    run: list[Moment] = []
    run_place = ""
    for m, place in zip(ordered, places, strict=True):
        if run and (
            place != run_place
            or m.taken_at - run[-1].taken_at > MAX_GAP
            or m.taken_at - run[0].taken_at > MAX_TRIP
        ):
            found.append((run_place, run))
            run = []
        if place is not None:
            run_place = place
            run.append(m)
    found.append((run_place, run))
    return [(place, t) for place, t in found if len(t) >= MIN_PHOTOS]


def _located(moments: Sequence[Moment]) -> tuple[list[Moment], list[str | None]]:
    ordered = by_time(moments)
    return ordered, _away_places(ordered, home_place(ordered))


def trips(moments: Sequence[Moment]) -> list[list[Moment]]:
    """Every trip away from home, oldest first, each in time order."""
    return [t for _, t in _trips(*_located(moments))]


def _months_at_home(ordered: Sequence[Moment], places: Sequence[str | None]) -> list[Memory]:
    """Each calendar month with twenty photos at home: all of that month (what its days list),
    with a cover from home."""
    in_month: Counter[tuple[int, int]] = Counter()
    at_home: defaultdict[tuple[int, int], list[Moment]] = defaultdict(list)
    for m, place in zip(ordered, places, strict=True):
        which = (m.taken_at.year, m.taken_at.month)
        in_month[which] += 1
        if place is None:
            at_home[which].append(m)
    found = []
    for (year, month), home in at_home.items():
        if len(home) >= MIN_AT_HOME:
            first, last = date(year, month, 1), date(year, month, monthrange(year, month)[1])
            found.append(
                Memory(
                    key=f"{first.isoformat()}_{last.isoformat()}",
                    title=period_words(first, first),
                    first_day=first,
                    last_day=last,
                    count=in_month[year, month],
                    cover_id=cover_of(home),
                )
            )
    return found


def dominant_place(moments: Sequence[Moment]) -> str | None:
    """The place most of the photos with one were taken at; a tie goes to the first seen."""
    places = Counter(m.place for m in by_time(moments) if m.place)
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
    ordered = by_time(trip)
    period = period_words(ordered[0].taken_at.date(), ordered[-1].taken_at.date())
    place = dominant_place(ordered)
    return f"{place}, {period}" if place else period


def cover_of(moments: Sequence[Moment]) -> int:
    """The first favourite, else the first photo (by time)."""
    ordered = by_time(moments)
    return next((m for m in ordered if m.favourite), ordered[0]).asset_id


def memory_of(trip: Sequence[Moment], place: str | None = None) -> Memory:
    """A trip as a memory, named after ``place`` (by default its photos' main place)."""
    ordered = by_time(trip)
    first, last = ordered[0].taken_at.date(), ordered[-1].taken_at.date()
    place = place or dominant_place(ordered)
    period = period_words(first, last)
    return Memory(
        key=f"{first.isoformat()}_{last.isoformat()}",
        title=f"{place}, {period}" if place else period,
        first_day=first,
        last_day=last,
        count=len(ordered),
        cover_id=cover_of(ordered),
    )


def _turn[T](items: Sequence[T], today: date, size: int) -> list[T]:
    """``size`` of ``items``, a different page each day. When they all fit, their order turns
    instead, so Home still changes from one day to the next."""
    n = len(items)
    if n == 0:
        return []
    step = size if n > size else 1
    start = (today.toordinal() * step) % n
    return [items[(start + i) % n] for i in range(min(size, n))]


def memories(moments: Sequence[Moment], today: date) -> list[Memory]:
    """What Home lists: the two newest memories, then the others' page for ``today``. Only the
    trips shown are named (a library holds hundreds)."""
    ordered, places = _located(moments)
    found: list[tuple[date, date, Memory | tuple[str, list[Moment]]]] = [
        (t[-1].taken_at.date(), t[0].taken_at.date(), (place, t))
        for place, t in _trips(ordered, places)
    ]
    found += [(m.last_day, m.first_day, m) for m in _months_at_home(ordered, places)]
    found.sort(key=lambda f: (f[0], f[1]), reverse=True)
    newest_first = [f[2] for f in found]
    head, rest = newest_first[:NEWEST_FIRST], newest_first[NEWEST_FIRST:]
    shown = head + _turn(rest, today, MAX_MEMORIES - NEWEST_FIRST)
    return [m if isinstance(m, Memory) else memory_of(m[1], m[0]) for m in shown]
