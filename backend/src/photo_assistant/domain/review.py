"""Photos held for review (issue 8): which ones wait for a person instead of joining the library.

Two reasons:
- a look-alike: a newly imported photo whose perceptual hash is at most
  ``MAX_LOOKALIKE_DISTANCE`` bits from a photo that was already in the library and was taken
  outside the grouping window of it. Photos that resemble each other and were taken within
  that window are bursts, whichever job hashed them; those belong to the groups, not here.
- clutter: the auto-tagger's best guess for the photo is a screenshot, document, receipt or
  meme. The reason is that tag's name.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence
from datetime import datetime
from itertools import accumulate

from photo_assistant.domain.grouping import NEAR_DUPLICATE_WINDOW, Shot
from photo_assistant.domain.tags import VOCABULARY, TagScore, TagSpec

LOOKALIKE = "lookalike"
# Stricter than grouping's 6: outside the grouping window there is no "taken minutes apart"
# check to back it up.
MAX_LOOKALIKE_DISTANCE = 4

# Hashes at most MAX_LOOKALIKE_DISTANCE bits apart agree on at least one of this many disjoint
# bands of bits (pigeonhole), so a new photo is only compared with hashes sharing a band.
_BANDS = MAX_LOOKALIKE_DISTANCE + 1
_BAND_BITS = 64 // _BANDS
_BAND_MASK = (1 << _BAND_BITS) - 1


def _bands(phash: int) -> list[int]:
    """One key per band (band value and band number in one int); the last band takes every
    remaining high bit."""
    last = _BANDS - 1
    keys = [((phash >> (n * _BAND_BITS)) & _BAND_MASK) * _BANDS + n for n in range(last)]
    return [*keys, (phash >> (last * _BAND_BITS)) * _BANDS + last]


def _distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class _SameHash:
    """The library photos sharing one hash, in time order."""

    def __init__(self, photos: Iterable[tuple[datetime, int]]) -> None:
        ordered = sorted(photos)
        self._times = [taken_at for taken_at, _ in ordered]
        ids = [asset_id for _, asset_id in ordered]
        self._oldest_until = list(accumulate(ids, min))
        self._oldest_from = list(accumulate(reversed(ids), min))[::-1]

    def oldest_outside_window(self, taken_at: datetime) -> int | None:
        """The smallest id among those not taken within the grouping window of ``taken_at``."""
        before = bisect_left(self._times, taken_at - NEAR_DUPLICATE_WINDOW)
        after = bisect_right(self._times, taken_at + NEAR_DUPLICATE_WINDOW)
        found = [self._oldest_until[before - 1]] if before else []
        if after < len(self._times):
            found.append(self._oldest_from[after])
        return min(found, default=None)


class _Library:
    """The library's hashes, findable by any band of their bits."""

    def __init__(self, library: Iterable[Shot]) -> None:
        photos: dict[int, list[tuple[datetime, int]]] = {}
        for shot in library:
            if shot.phash is not None:
                photos.setdefault(int(shot.phash, 16), []).append((shot.taken_at, shot.asset_id))
        self._same = {phash: _SameHash(found) for phash, found in photos.items()}
        self._by_band: dict[int, list[int]] = {}
        for phash in self._same:
            for key in _bands(phash):
                self._by_band.setdefault(key, []).append(phash)

    def most_like(self, phash: int, taken_at: datetime) -> int | None:
        candidates = {other for key in _bands(phash) for other in self._by_band.get(key, ())}
        best: tuple[int, int] | None = None  # (distance, asset id): closest, then oldest
        for other in candidates:
            distance = _distance(phash, other)
            if distance > MAX_LOOKALIKE_DISTANCE:
                continue
            oldest = self._same[other].oldest_outside_window(taken_at)
            if oldest is not None and (best is None or (distance, oldest) < best):
                best = (distance, oldest)
        return None if best is None else best[1]


def lookalikes(new: Sequence[Shot], library: Sequence[Shot]) -> dict[int, int]:
    """new photo id → the library photo it most resembles (the oldest on a tie), for those
    close enough; library photos taken within the grouping window of the new one do not
    count. Photos without a hash resemble nothing."""
    known = _Library(library)
    found: dict[int, int] = {}
    for shot in new:
        like = None if shot.phash is None else known.most_like(int(shot.phash, 16), shot.taken_at)
        if like is not None:
            found[shot.asset_id] = like
    return found


def clutter_reason(
    tags: Sequence[TagScore], vocabulary: Sequence[TagSpec] = VOCABULARY
) -> str | None:
    """The clutter tag when it is the best of ``tags`` (best first), else None."""
    clutter = {spec.name for spec in vocabulary if spec.screen_or_document}
    return tags[0].name if tags and tags[0].name in clutter else None
