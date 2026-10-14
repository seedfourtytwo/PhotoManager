"""On this day (Home, issue 54): the photos taken on today's date in an earlier year.

Of the earlier years, the one with the most photos on the day wins (a tie: the most recent).
When no year has any, three days either side of the date count instead, and the answer says
it is not the day itself. 29 February is 28 February in the other years.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from photo_assistant.domain.memories import Moment, by_time, cover_of, dominant_place

AROUND = timedelta(days=3)  # either side of the date, when nothing was taken on the day
DAY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class OnThisDay:
    day: date  # today's date in that year
    years_ago: int
    exact: bool  # False: the days around it
    first_day: date  # the photos are exactly those taken from first_day to last_day
    last_day: date
    photos: tuple[Moment, ...]  # in time order

    @property
    def count(self) -> int:
        return len(self.photos)

    @property
    def cover_id(self) -> int:
        return cover_of(self.photos)

    @property
    def place(self) -> str | None:
        return dominant_place(self.photos)


def anniversary(today: date, year: int) -> date:
    """Today's month and day in ``year``."""
    if (today.month, today.day) == (2, 29):
        try:
            return date(year, 2, 29)
        except ValueError:
            return date(year, 2, 28)
    return today.replace(year=year)


def on_this_day(moments: Sequence[Moment], today: date) -> OnThisDay | None:
    by_day: dict[date, list[Moment]] = defaultdict(list)
    for m in moments:
        by_day[m.taken_at.date()].append(m)
    # the days around 1 January reach back into the year before: count from the year after
    years = sorted({d.year for d in by_day} | {d.year + 1 for d in by_day}, reverse=True)
    earlier = [y for y in years if 1 < y < today.year]
    return _best(by_day, today, earlier, exact=True) or _best(by_day, today, earlier, exact=False)


def _best(
    by_day: Mapping[date, list[Moment]], today: date, years: Sequence[int], *, exact: bool
) -> OnThisDay | None:
    """The year (of ``years``, newest first) with the most photos; on a tie the newest stays."""
    picked: OnThisDay | None = None
    for year in years:
        day = anniversary(today, year)
        first, last = (day, day) if exact else (day - AROUND, day + AROUND)
        days = (first + n * DAY for n in range((last - first).days + 1))
        found = [m for d in days for m in by_day.get(d, ())]
        if found and (picked is None or len(found) > picked.count):
            ordered = tuple(by_time(found))
            picked = OnThisDay(day, today.year - year, exact, first, last, ordered)
    return picked
