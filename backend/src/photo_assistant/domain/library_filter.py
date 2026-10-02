"""What the timeline, facets, calendar, map and bulk downloads can be narrowed by (FEATURES 3.2).

The filter is plain data; the repository turns it into SQL *after* the visibility rule.
"""

from dataclasses import dataclass
from datetime import date

from photo_assistant.domain.model import MAX_ID

MAX_SEARCH_TERMS = 8
MAX_SEARCH_LENGTH = 200


@dataclass(frozen=True, slots=True)
class AssetFilter:
    from_day: date | None = None  # inclusive
    to_day: date | None = None  # inclusive
    year: int | None = None
    month: int | None = None  # needs year
    source_ids: tuple[int, ...] = ()
    camera: str | None = None  # exact camera model
    place: str | None = None  # country, region or city, any case
    q: str | None = None  # free text
    favourite: bool | None = None
    hidden: bool | None = None  # None: my hidden photos are left out
    guessed_date: bool | None = None  # True: only dates taken from the file's mtime
    has_location: bool | None = None


def filter_problem(f: AssetFilter) -> str | None:
    """A sentence saying why the filter makes no sense, or None."""
    if f.month is not None and f.year is None:
        return "a month needs a year"
    if f.month is not None and not 1 <= f.month <= 12:
        return "month must be 1 to 12"
    if f.year is not None and not 1800 <= f.year <= 9999:
        return "year out of range"
    if f.from_day and f.to_day and f.from_day > f.to_day:
        return "'from' must be on or before 'to'"
    if f.q is not None and len(f.q) > MAX_SEARCH_LENGTH:
        return "search text is too long"
    if any(not 1 <= s <= MAX_ID for s in f.source_ids):
        return "no such source"
    return None


def search_terms(q: str | None) -> list[str]:
    """Every word must match somewhere (file name, place, camera, album title)."""
    return (q or "").split()[:MAX_SEARCH_TERMS]


def like_pattern(term: str) -> str:
    """``%term%`` for SQL LIKE with ``\\`` as the escape character."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
