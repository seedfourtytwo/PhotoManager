"""Years on Home (issue 54): each calendar year with ten dated photos, as a memory of the whole
year ("2016", 1 January to 31 December), newest first. Needs dates only, no places.

The cover is a favourite of that year when it has one, else one of its photos that changes
each day: the row looks alive while staying the same all day.
"""

from collections.abc import Sequence
from datetime import MAXYEAR, date, datetime

from photo_assistant.domain.memories import MIN_PHOTOS, Memory, Moment, index_at


def years(moments: Sequence[Moment], today: date) -> list[Memory]:
    """``moments`` in time order; a bisection finds each year, so this is a few look-ups a year
    and one look over the photos of the years shown, for their favourites."""
    found: list[Memory] = []
    day = today.toordinal()
    start = 0
    while start < len(moments):
        year = moments[start].taken_at.year
        last = year == MAXYEAR
        end = len(moments) if last else index_at(moments, datetime(year + 1, 1, 1), start)
        if end - start >= MIN_PHOTOS:
            found.append(_year(year, moments[start:end], day))
        start = end
    return found[::-1]


def _year(year: int, photos: Sequence[Moment], day: int) -> Memory:
    first, last = date(year, 1, 1), date(year, 12, 31)
    loved = [m for m in photos if m.favourite] or photos
    return Memory(
        key=f"{first.isoformat()}_{last.isoformat()}",
        title=str(year),
        first_day=first,
        last_day=last,
        count=len(photos),
        cover_id=loved[day % len(loved)].asset_id,
    )
