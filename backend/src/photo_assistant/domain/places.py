"""Places: where a photo was taken, as names (FEATURES 2.4), and Places as one list."""

import math
from dataclasses import dataclass
from typing import Literal

PlaceKind = Literal["country", "city"]


@dataclass(frozen=True, slots=True)
class Place:
    country: str
    region: str = ""
    city: str = ""

    @property
    def label(self) -> str:
        return ", ".join(part for part in (self.city, self.region, self.country) if part)


@dataclass(frozen=True, slots=True)
class PlaceGroup:
    """The photos of one (country, city) a viewer may see; ``city`` is "" for none."""

    country: str
    city: str
    count: int
    located: int  # how many of them have GPS
    lat: float | None  # the mean position of those, None when none has one
    lon: float | None
    cover_id: int | None  # the newest one with a thumbnail, None when none has one yet
    cover_taken: str | None  # its taken_at (ISO): orders covers across cities


@dataclass(frozen=True, slots=True)
class PlaceTally:
    """A country or a city as Places lists it."""

    name: str
    kind: PlaceKind
    country: str  # the country itself, or the city's country
    count: int
    cover_id: int | None
    lat: float | None
    lon: float | None


def _centre(groups: list[PlaceGroup]) -> tuple[float | None, float | None]:
    """Mean of the group centres weighted by located photos. The longitude is a circular mean,
    so a country across the date line (Fiji) is centred on it, not on the far side."""
    located = [(g.located, g.lat, g.lon) for g in groups if g.located]
    points = [(n, lat, lon) for n, lat, lon in located if lat is not None and lon is not None]
    total = sum(n for n, _, _ in points)
    if not total:
        return None, None
    lat = sum(n * la for n, la, _ in points) / total
    x = sum(n * math.cos(math.radians(lo)) for n, _, lo in points)
    y = sum(n * math.sin(math.radians(lo)) for n, _, lo in points)
    return lat, math.degrees(math.atan2(y, x))


def _cover(groups: list[PlaceGroup]) -> int | None:
    """The newest cover; on the same moment, the higher id (the later import)."""
    covers = [(g.cover_taken or "", g.cover_id) for g in groups if g.cover_id is not None]
    return max(covers)[1] if covers else None


def _tally(name: str, kind: PlaceKind, country: str, groups: list[PlaceGroup]) -> PlaceTally:
    lat, lon = _centre(groups)
    count = sum(g.count for g in groups)
    return PlaceTally(name, kind, country, count, _cover(groups), lat, lon)


def tally_places(groups: list[PlaceGroup]) -> list[PlaceTally]:
    """Every country and every city once, most photos first (then countries before cities,
    then by name). Photos with a country but no city count towards the country only."""
    countries: dict[str, list[PlaceGroup]] = {}
    for g in groups:
        countries.setdefault(g.country, []).append(g)
    found = [_tally(c, "country", c, gs) for c, gs in countries.items()]
    found += [_tally(g.city, "city", g.country, [g]) for g in groups if g.city]
    return sorted(found, key=lambda p: (-p.count, p.kind != "country", p.name))
