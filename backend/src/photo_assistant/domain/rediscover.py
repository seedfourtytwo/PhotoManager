"""Rediscover on Home (issue 54): a dozen photos from across the years, a new dozen each day.

The years take turns: one photo from each year before a second from any of them, each from a
month of its year not picked yet. Within a month a favourite wins. Which years, months and
photos come up turns with the date, so Rediscover stays the same all day and changes the next.
The last 30 days are left to New this week and the Library, unless there is nothing older.
The answer leads with a favourite when one was picked (Home shows the first one large); the
rest follow oldest first, a walk through the years.
"""

from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import MAXYEAR, date, datetime, timedelta
from itertools import islice

from photo_assistant.domain.memories import Moment, by_time, index_at

RECENT = timedelta(days=30)  # newer photos are on Home already, under New this week
SHOWN = 12

Span = tuple[int, int]  # the photos moments[start:end]


def rediscover(moments: Sequence[Moment], today: date) -> list[Moment]:
    """What Rediscover shows on ``today`` from ``moments`` (in time order, as Home reads them)."""
    recent = index_at(moments, datetime.combine(today - RECENT, datetime.min.time()))
    pool = moments[:recent] or moments
    if not pool:
        return []
    day = today.toordinal()
    months = _months_by_year(pool)
    years = _turned(sorted(months), day)
    turns = [_turned(months[year], day) for year in years]
    picked = [_pick(pool[a:b], day) for a, b in islice(_in_turn(turns), SHOWN)]
    lead = next((m for m in picked if m.favourite), picked[0])
    return [lead, *by_time(m for m in picked if m is not lead)]


def _months_by_year(pool: Sequence[Moment]) -> dict[int, list[Span]]:
    """Each month that has photos, by year: a bisection per month, never a pass over all."""
    found: defaultdict[int, list[Span]] = defaultdict(list)
    start = 0
    while start < len(pool):
        at = pool[start].taken_at
        if (at.year, at.month) == (MAXYEAR, 12):
            end = len(pool)
        else:
            after = datetime(at.year + at.month // 12, at.month % 12 + 1, 1)
            end = index_at(pool, after, start)
        found[at.year].append((start, end))
        start = end
    return found


def _turned[T](items: Sequence[T], day: int) -> list[T]:
    """``items`` starting at a different one each day."""
    k = day % len(items)
    return [*items[k:], *items[:k]]


def _in_turn(turns: Sequence[Sequence[Span]]) -> Iterator[Span]:
    """The first month of each year, then the second of each, and so on."""
    for round_ in range(max(map(len, turns))):
        yield from (months[round_] for months in turns if round_ < len(months))


def _pick(month: Sequence[Moment], day: int) -> Moment:
    loved = [m for m in month if m.favourite] or month
    return loved[day % len(loved)]
