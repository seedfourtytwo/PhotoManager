"""Bursts and near-duplicates (FEATURES 2.5).

Two photos belong together when they are
- a burst: the same camera model within ``BURST_SECONDS`` of each other, or
- near-duplicates: perceptual hashes at most ``MAX_PHASH_DISTANCE`` bits apart and taken
  within ``NEAR_DUPLICATE_WINDOW`` of each other.
Membership is transitive (a long burst is one group). A group is named by its smallest id.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

BURST_SECONDS = 3.0
MAX_PHASH_DISTANCE = 6
NEAR_DUPLICATE_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class Shot:
    asset_id: int
    taken_at: datetime
    camera: str | None
    phash: str | None  # 64-bit hex


def phash_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _related(a: Shot, b: Shot) -> bool:
    gap = abs((b.taken_at - a.taken_at).total_seconds())
    if a.camera is not None and a.camera == b.camera and gap <= BURST_SECONDS:
        return True
    return (
        a.phash is not None
        and b.phash is not None
        and gap <= NEAR_DUPLICATE_WINDOW.total_seconds()
        and phash_distance(a.phash, b.phash) <= MAX_PHASH_DISTANCE
    )


def _root(parent: dict[int, int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def group_shots(shots: Sequence[Shot]) -> dict[int, int | None]:
    """asset id → group id (smallest id in its group), or None for a photo on its own."""
    ordered = sorted(shots, key=lambda s: (s.taken_at, s.asset_id))
    parent = {s.asset_id: s.asset_id for s in ordered}
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if b.taken_at - a.taken_at > NEAR_DUPLICATE_WINDOW:
                break
            if _related(a, b):
                ra, rb = _root(parent, a.asset_id), _root(parent, b.asset_id)
                parent[max(ra, rb)] = min(ra, rb)
    roots = {s.asset_id: _root(parent, s.asset_id) for s in ordered}
    sizes: dict[int, int] = {}
    for r in roots.values():
        sizes[r] = sizes.get(r, 0) + 1
    return {i: (r if sizes[r] > 1 else None) for i, r in roots.items()}
