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


_EPOCH = datetime(1970, 1, 1)
_MICRO = timedelta(microseconds=1)
_BURST_US = int(BURST_SECONDS * 1_000_000)
_WINDOW_US = NEAR_DUPLICATE_WINDOW // _MICRO


def _micros(t: datetime) -> int:
    """Wall-clock time as whole microseconds: exact, and no time zone involved."""
    return (t.replace(tzinfo=None) - _EPOCH) // _MICRO


def _root(parent: dict[int, int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def group_shots(shots: Sequence[Shot]) -> dict[int, int | None]:
    """asset id → group id (smallest id in its group), or None for a photo on its own.

    Times and hashes are turned into plain ints once (C29: 6.2 s → 0.2 s for 51k photos);
    each photo is compared only with the ones up to the window after it."""
    ordered = sorted(shots, key=lambda s: (s.taken_at, s.asset_id))
    ids = [s.asset_id for s in ordered]
    times = [_micros(s.taken_at) for s in ordered]
    cameras = [s.camera for s in ordered]
    hashes = [int(s.phash, 16) if s.phash is not None else None for s in ordered]
    parent = {i: i for i in ids}
    for i in range(len(ordered)):
        t, camera, phash = times[i], cameras[i], hashes[i]
        for j in range(i + 1, len(ordered)):
            gap = times[j] - t
            if gap > _WINDOW_US:
                break
            burst = camera is not None and camera == cameras[j] and gap <= _BURST_US
            other = hashes[j]
            near = phash is not None and other is not None
            if burst or (near and (phash ^ other).bit_count() <= MAX_PHASH_DISTANCE):  # type: ignore[operator]
                ra, rb = _root(parent, ids[i]), _root(parent, ids[j])
                parent[max(ra, rb)] = min(ra, rb)
    roots = {i: _root(parent, i) for i in ids}
    sizes: dict[int, int] = {}
    for r in roots.values():
        sizes[r] = sizes.get(r, 0) + 1
    return {i: (r if sizes[r] > 1 else None) for i, r in roots.items()}


def runs_with(
    times: Sequence[tuple[int, datetime]], new: set[int]
) -> list[tuple[datetime, datetime]]:
    """The time ranges (inclusive) of the runs of photos holding a new one.

    A run is a stretch of photos in time order where each is at most the window after the one
    before it. No group can reach across a longer gap (both rules need the window), so new
    photos can only change groups inside their runs."""
    ordered = sorted(times, key=lambda x: (x[1], x[0]))
    runs: list[tuple[datetime, datetime]] = []
    start = 0
    for k in range(1, len(ordered) + 1):
        if k == len(ordered) or ordered[k][1] - ordered[k - 1][1] > NEAR_DUPLICATE_WINDOW:
            if any(i in new for i, _ in ordered[start:k]):
                runs.append((ordered[start][1], ordered[k - 1][1]))
            start = k
    return runs


def regroup_runs(shots: Sequence[Shot]) -> dict[int, int | None]:
    """Groups for every photo of some complete runs (``runs_with``): the same answer the
    whole library would give for them."""
    return group_shots(shots)
