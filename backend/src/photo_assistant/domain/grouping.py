"""Bursts and near-duplicates (FEATURES 2.5).

Two photos belong together when they are
- a burst: the same camera model within ``BURST_SECONDS`` of each other, or
- near-duplicates: perceptual hashes at most ``MAX_PHASH_DISTANCE`` bits apart and taken
  within ``NEAR_DUPLICATE_WINDOW`` of each other.
Membership is transitive (a long burst is one group). A group is named by its smallest id.
"""

from collections import deque
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


# Hashes at most MAX_PHASH_DISTANCE bits apart agree on at least one of this many disjoint
# blocks of bits (pigeonhole), so only hashes sharing a block are ever compared.
_BLOCKS = MAX_PHASH_DISTANCE + 1
_BLOCK_BITS = 64 // _BLOCKS
_BLOCK_MASK = (1 << _BLOCK_BITS) - 1


def _blocks(phash: int) -> list[int]:
    """One key per block (block value and block number in one int); the last block takes
    every remaining high bit."""
    last = _BLOCKS - 1
    keys = [((phash >> (n * _BLOCK_BITS)) & _BLOCK_MASK) * _BLOCKS + n for n in range(last)]
    return [*keys, (phash >> (last * _BLOCK_BITS)) * _BLOCKS + last]


class _RecentHashes:
    """The distinct hashes seen in the last window, each with its latest photo.

    The latest photo is enough: earlier photos with that hash inside the window were already
    joined to it one after the other."""

    def __init__(self) -> None:
        self._latest: dict[int, tuple[int, int, list[int]]] = {}  # hash -> time, id, blocks
        self._by_block: dict[int, set[int]] = {}
        self._seen: deque[tuple[int, int]] = deque()  # (time, hash), oldest first

    def forget_before(self, earliest: int) -> None:
        seen, latest = self._seen, self._latest
        while seen and seen[0][0] < earliest:
            at, phash = seen.popleft()
            entry = latest.get(phash)
            if entry is None or entry[0] != at:
                continue  # seen again since
            del latest[phash]
            for key in entry[2]:
                self._by_block[key].discard(phash)

    def add(self, phash: int, at: int, asset_id: int) -> list[int]:
        """Remember this photo; the asset ids it has to be joined to."""
        known = self._latest.get(phash)
        self._seen.append((at, phash))
        if known is not None:
            # the same picture again: whatever is near was joined when it first came (or
            # joined itself to that photo since), so the previous one is all it takes
            self._latest[phash] = (at, asset_id, known[2])
            return [known[1]]
        keys = _blocks(phash)
        buckets = [self._by_block.setdefault(key, set()) for key in keys]
        candidates = set().union(*buckets)
        joined = [
            self._latest[other][1]
            for other in candidates
            if (phash ^ other).bit_count() <= MAX_PHASH_DISTANCE
        ]
        for bucket in buckets:
            bucket.add(phash)
        self._latest[phash] = (at, asset_id, keys)
        return joined


def group_shots(shots: Sequence[Shot]) -> dict[int, int | None]:
    """asset id → group id (smallest id in its group), or None for a photo on its own.

    One pass in time order, never comparing every pair inside a window: a burst is found
    from the previous photo of the same camera, a near-duplicate from the recent hashes that
    share a block of bits (8,000 photos in five minutes: 7 s → well under a second)."""
    ordered = sorted(shots, key=lambda s: (s.taken_at, s.asset_id))
    parent = {s.asset_id: s.asset_id for s in ordered}
    last_of_camera: dict[str, tuple[int, int]] = {}  # camera -> (time, asset id)
    recent = _RecentHashes()

    def join(a: int, b: int) -> None:
        ra, rb = _root(parent, a), _root(parent, b)
        parent[max(ra, rb)] = min(ra, rb)

    for shot in ordered:
        at, asset_id = _micros(shot.taken_at), shot.asset_id
        if shot.camera is not None:
            before = last_of_camera.get(shot.camera)
            if before is not None and at - before[0] <= _BURST_US:
                join(asset_id, before[1])
            last_of_camera[shot.camera] = (at, asset_id)
        if shot.phash is not None:
            phash = int(shot.phash, 16)
            recent.forget_before(at - _WINDOW_US)
            for other in recent.add(phash, at, asset_id):
                join(asset_id, other)
    roots = {i: _root(parent, i) for i in parent}
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
