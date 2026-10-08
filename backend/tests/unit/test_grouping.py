"""Bursts and near-duplicates (FEATURES 2.5): which photos share a group."""

import random
import time
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from photo_assistant.domain.grouping import (
    NEAR_DUPLICATE_WINDOW,
    Shot,
    group_shots,
    phash_distance,
    runs_with,
)

T0 = datetime(2024, 5, 1, 10, 0, 0)
A = "0000000000000000"


def shot(i: int, seconds: float, camera: str | None = "Pixel", phash: str | None = None) -> Shot:
    return Shot(i, T0 + timedelta(seconds=seconds), camera, phash)


def test_phash_distance_counts_differing_bits() -> None:
    assert phash_distance(A, A) == 0
    assert phash_distance(A, "000000000000000f") == 4
    assert phash_distance(A, "ffffffffffffffff") == 64


def test_same_camera_within_three_seconds_is_a_burst() -> None:
    groups = group_shots([shot(1, 0), shot(2, 2), shot(3, 4.5), shot(4, 20)])
    assert groups == {1: 1, 2: 1, 3: 1, 4: None}, "chains: 0-2-4.5 s are one burst"


def test_different_or_unknown_cameras_are_not_a_burst() -> None:
    groups = group_shots(
        [shot(1, 0, "Pixel"), shot(2, 1, "iPhone"), shot(3, 1.5, None), shot(4, 2, None)]
    )
    assert set(groups.values()) == {None}


def test_similar_pictures_within_ten_minutes_are_near_duplicates() -> None:
    near = "0000000000000007"  # 3 bits away
    far = "ffff000000000000"  # 16 bits away
    groups = group_shots(
        [
            shot(1, 0, "a", A),
            shot(2, 500, "b", near),
            shot(3, 520, "c", far),
            shot(4, 700, "d", A),  # similar to 1 but 11+ minutes later: only via 2 (200 s)
            shot(5, 5000, "e", A),
        ]
    )
    assert groups == {1: 1, 2: 1, 3: None, 4: 1, 5: None}


def test_group_id_is_the_smallest_member_and_order_does_not_matter() -> None:
    shots = [shot(9, 0), shot(3, 1), shot(7, 2)]
    assert group_shots(shots) == group_shots(list(reversed(shots))) == {9: 3, 3: 3, 7: 3}


# --- C29: fast grouping, and regrouping only where new photos landed ----------------------------


def reference_groups(shots: list[Shot]) -> dict[int, int | None]:
    """The original (slow) algorithm, kept as the oracle."""
    ordered = sorted(shots, key=lambda s: (s.taken_at, s.asset_id))
    parent = {s.asset_id: s.asset_id for s in ordered}

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            gap = (b.taken_at - a.taken_at).total_seconds()
            if gap > NEAR_DUPLICATE_WINDOW.total_seconds():
                break
            burst = a.camera is not None and a.camera == b.camera and gap <= 3.0
            near = (
                a.phash is not None
                and b.phash is not None
                and phash_distance(a.phash, b.phash) <= 6
            )
            if burst or near:
                ra, rb = root(a.asset_id), root(b.asset_id)
                parent[max(ra, rb)] = min(ra, rb)
    roots = {s.asset_id: root(s.asset_id) for s in ordered}
    sizes: dict[int, int] = {}
    for r in roots.values():
        sizes[r] = sizes.get(r, 0) + 1
    return {i: (r if sizes[r] > 1 else None) for i, r in roots.items()}


SHOTS = st.lists(
    st.tuples(
        st.integers(0, 4000),  # seconds after T0: dense enough for bursts and chains
        st.sampled_from(["Pixel", "iPhone", None]),
        st.sampled_from([None, A, "000000000000000f", "00000000000000ff", "ffffffffffffffff"]),
    ),
    max_size=40,
).map(lambda xs: [shot(i + 1, t, c, p) for i, (t, c, p) in enumerate(xs)])


@settings(max_examples=150, deadline=None)
@given(SHOTS)
def test_fast_grouping_is_identical_to_the_original(shots: list[Shot]) -> None:
    assert group_shots(shots) == reference_groups(shots)


@settings(max_examples=150, deadline=None)
@given(SHOTS, st.data())
def test_regrouping_only_the_runs_with_new_photos_gives_the_full_result(
    shots: list[Shot], data: st.DataObject
) -> None:
    new = set(data.draw(st.sets(st.sampled_from([s.asset_id for s in shots]))) if shots else set())
    old = [s for s in shots if s.asset_id not in new]
    groups = group_shots(old)
    runs = runs_with([(s.asset_id, s.taken_at) for s in shots], new)
    touched = [s for s in shots if any(lo <= s.taken_at <= hi for lo, hi in runs)]
    groups |= group_shots(touched)
    assert groups == group_shots(shots)
    for s in shots:  # every new photo lies in a run that was regrouped
        assert s.asset_id not in new or any(lo <= s.taken_at <= hi for lo, hi in runs)


# --- a dense time window (a timelapse, a batch of screenshots) must not go quadratic ------------

_FLIPS = st.lists(st.integers(0, 63), max_size=5, unique=True)
_NEAR_HASHES = st.tuples(st.sampled_from([0, 0xFFFF0000FFFF0000, 0x123456789ABCDEF0]), _FLIPS).map(
    lambda base_bits: f"{base_bits[0] ^ sum(1 << b for b in base_bits[1]):016x}"
)
DENSE_SHOTS = st.lists(
    st.tuples(
        st.integers(0, 1_500_000),  # milliseconds: several shots per window, some in a burst
        st.sampled_from(["Pixel", "iPhone", None]),
        st.one_of(st.none(), _NEAR_HASHES),
    ),
    max_size=60,
).map(lambda xs: [shot(i + 1, ms / 1000, c, p) for i, (ms, c, p) in enumerate(xs)])


@settings(max_examples=400, deadline=None)
@given(DENSE_SHOTS)
def test_grouping_of_clustered_hashes_is_identical_to_the_original(shots: list[Shot]) -> None:
    """Hashes a few bits apart, up to and past the limit, in and across windows."""
    assert group_shots(shots) == reference_groups(shots)


def test_grouping_on_the_edges_of_both_rules() -> None:
    six, seven = f"{0b111111:016x}", f"{0b1111111:016x}"
    edge = [
        shot(1, 0, "a", A),
        shot(2, 600, "b", six),  # exactly the window, exactly the distance: grouped
        shot(3, 1200.000001, "c", A),  # one microsecond past the window after 2
        shot(4, 1203.000001, "c", seven),  # exactly three seconds: a burst with 3
        shot(5, 1206.000002, "c", None),  # a microsecond too late for the burst
    ]
    assert group_shots(edge) == reference_groups(edge) == {1: 1, 2: 1, 3: 3, 4: 3, 5: None}


def _timed(shots: list[Shot]) -> tuple[dict[int, int | None], float]:
    started = time.perf_counter()
    groups = group_shots(shots)
    return groups, time.perf_counter() - started


def test_eight_thousand_photos_in_five_minutes_are_grouped_quickly() -> None:
    """Was 7 s (every pair inside the window compared); a full regroup is queued on every
    trash, restore and date fix."""
    rng = random.Random(8)
    cameras = ["Pixel", "iPhone", None]
    shots = [
        shot(i, rng.uniform(0, 300), rng.choice(cameras), f"{rng.getrandbits(64):016x}")
        for i in range(1, 8001)
    ]
    groups, seconds = _timed(shots)
    assert seconds < 2.0, f"{seconds:.2f} s"
    assert sum(g is not None for g in groups.values()) > 5000, "bursts all over"


def test_a_timelapse_of_identical_pictures_is_grouped_quickly() -> None:
    shots = [shot(i, i * 0.03, None, A) for i in range(1, 8001)]
    groups, seconds = _timed(shots)
    assert seconds < 2.0, f"{seconds:.2f} s"
    assert set(groups.values()) == {1}
