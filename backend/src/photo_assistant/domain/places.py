"""Places: where a photo was taken, as names (FEATURES 2.4)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Place:
    country: str
    region: str = ""
    city: str = ""

    @property
    def label(self) -> str:
        return ", ".join(part for part in (self.city, self.region, self.country) if part)
