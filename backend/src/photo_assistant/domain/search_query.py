"""Split a search box query into facets (``person:Lea``, ``date:2023``) and free text.

Facets become SQL filters on the candidate set; the free text goes to the CLIP text encoder
(ARCHITECTURE §4 Search). Anything that isn't a well-formed known facet stays in the text, so
"dinner at 19:30" is never mangled.

Names the library knows (people, places, albums, tags) are also spotted in the plain words, so
"Lea at the beach" needs no ``person:``.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date

from photo_assistant.domain.errors import DomainError
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


@dataclass(frozen=True, slots=True)
class Spotted:
    text: str  # the words no name used
    names: tuple[tuple[str, str], ...]  # (kind, the name as the library spells it), as typed


_EDGES = re.compile(r"^[\W_]+|[\W_]+$")


def _key(word: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))
    return _EDGES.sub("", plain.casefold())


def name_key(name: str) -> tuple[str, ...]:
    """A name as names are compared: whole words, no case, no accents, no punctuation round them."""
    return tuple(k for k in map(_key, name.split()) if k)


def spot_names(text: str, known: Mapping[str, Iterable[str]]) -> Spotted:
    """The known names that appear as whole words in ``text``, and the words left without them.
    The longest name wins; between kinds with the same name, the kind listed first."""
    names: dict[tuple[str, ...], tuple[str, str]] = {}
    for kind, spellings in known.items():
        for name in spellings:
            if key := name_key(name):
                names.setdefault(key, (kind, name))
    words = text.split()
    tokens = [(i, k) for i, word in enumerate(words) if (k := _key(word))]
    longest = max(map(len, names), default=0)
    found: list[tuple[str, str]] = []
    used: set[int] = set()
    t = 0
    while t < len(tokens):
        for n in range(min(longest, len(tokens) - t), 0, -1):
            hit = names.get(tuple(k for _, k in tokens[t : t + n]))
            if hit is not None:
                if hit not in found:
                    found.append(hit)
                used.update(range(tokens[t][0], tokens[t + n - 1][0] + 1))
                t += n
                break
        else:
            t += 1
    left = " ".join(word for i, word in enumerate(words) if i not in used)
    return Spotted(left, tuple(found))


class InvalidFacetError(DomainError):
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
