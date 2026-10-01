"""Split a search box query into facets (``person:Lea``, ``date:2023``) and free text.

Facets become SQL filters on the candidate set; the free text goes to the CLIP text encoder
(ARCHITECTURE §4 Search). Anything that isn't a well-formed known facet stays in the text, so
"dinner at 19:30" is never mangled.
"""

import re
from dataclasses import dataclass

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
