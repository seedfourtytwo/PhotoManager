"""Split a search box query into facets (``person:Lea``, ``date:2023``) and free text.

Facets become SQL filters on the candidate set; the free text goes to the CLIP text encoder
(ARCHITECTURE §4 Search). Anything that isn't a well-formed known facet stays in the text, so
"dinner at 19:30" is never mangled.
"""

import re
from dataclasses import dataclass, replace
from datetime import date

from photo_assistant.domain.library_filter import AssetFilter

FACETS: tuple[str, ...] = ("date", "person", "place", "tag", "camera")
_ALIASES = {"year": "date"}
_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")
_TOKEN = re.compile(r'(?P<key>[A-Za-z]+):(?:"(?P<quoted>[^"]+)"|(?P<bare>[^\s"]+))|(?P<word>\S+)')


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    text: str
    facets: tuple[tuple[str, str], ...]

    def values(self, facet: str) -> list[str]:
        return [value for key, value in self.facets if key == facet]


def _facet(key: str, value: str) -> tuple[str, str] | None:
    name = _ALIASES.get(key.lower(), key.lower())
    if name not in FACETS:
        return None
    if name == "date" and not _DATE.fullmatch(value):
        return None
    return name, value


def parse_query(q: str) -> ParsedQuery:
    words: list[str] = []
    facets: list[tuple[str, str]] = []
    for match in _TOKEN.finditer(q):
        key = match.group("key")
        value = match.group("quoted") or match.group("bare")
        facet = _facet(key, value) if key and value else None
        if facet is None:
            words.append(match.group(0))
        else:
            facets.append(facet)
    return ParsedQuery(" ".join(words), tuple(facets))


class InvalidFacetError(ValueError):
    """A facet that looks right but names an impossible value (``date:2021-13``)."""


def _date_filter(f: AssetFilter, value: str) -> AssetFilter:
    parts = [int(p) for p in value.split("-")]
    try:
        if len(parts) == 3:
            day = date(*parts)
            return replace(f, year=None, month=None, from_day=day, to_day=day)
        if len(parts) == 2:
            date(parts[0], parts[1], 1)
            return replace(f, year=parts[0], month=parts[1], from_day=None, to_day=None)
    except ValueError as exc:
        raise InvalidFacetError(f"date:{value} is not a real date") from exc
    return replace(f, year=parts[0], month=None, from_day=None, to_day=None)


def with_facets(base: AssetFilter, parsed: ParsedQuery) -> AssetFilter:
    """The library filter narrowed by the date, place and camera facets (the last one of each
    kind wins). ``person`` and ``tag`` are answered by the ML store, not by SQL."""
    f = base
    for key, value in parsed.facets:
        if key == "date":
            f = _date_filter(f, value)
        elif key == "place":
            f = replace(f, place=value)
        elif key == "camera":
            f = replace(f, camera=value)
    return f
