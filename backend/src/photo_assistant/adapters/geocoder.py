"""Offline reverse geocoding from the GeoNames cities (population > 1000) that ship with the
``reverse_geocoder`` package. No network, ever.

We read its data file ourselves and search a k-d tree of points on the unit sphere, so
distances are true (chord) distances and the library's global singleton is not needed.
"""

import csv
import math
import threading
from collections.abc import Sequence
from importlib import resources

import pycountry
from scipy.spatial import cKDTree  # type: ignore[import-untyped]

from photo_assistant.domain.places import Place

EARTH_RADIUS_KM = 6371.0


def _unit(lat: float, lon: float) -> tuple[float, float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    return (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi))


def country_name(code: str) -> str:
    country = pycountry.countries.get(alpha_2=code)
    if country is None:
        return code
    return str(getattr(country, "common_name", None) or country.name)


class OfflineGeocoder:
    def __init__(self, max_distance_km: float = 50.0) -> None:
        # A photo in the middle of the sea is not "in" the nearest town.
        self._max_chord = 2 * math.sin(max_distance_km / EARTH_RADIUS_KM / 2)
        self._lock = threading.Lock()
        self._tree: cKDTree | None = None
        self._places: list[Place] = []

    def _load(self) -> cKDTree:
        with self._lock:
            if self._tree is None:
                data = resources.files("reverse_geocoder") / "rg_cities1000.csv"
                points, places = [], []
                with data.open(encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        points.append(_unit(float(row["lat"]), float(row["lon"])))
                        places.append(Place(country_name(row["cc"]), row["admin1"], row["name"]))
                self._places = places
                self._tree = cKDTree(points)
            return self._tree

    def places_for(self, points: Sequence[tuple[float, float]]) -> list[Place | None]:
        if not points:
            return []
        tree = self._load()
        distances, indices = tree.query([_unit(lat, lon) for lat, lon in points], k=1)
        return [
            self._places[int(i)] if d <= self._max_chord else None
            for d, i in zip(distances, indices, strict=True)
        ]
