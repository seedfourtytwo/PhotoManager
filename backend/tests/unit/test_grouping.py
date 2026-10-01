"""Bursts and near-duplicates (FEATURES 2.5): which photos share a group."""

from datetime import datetime, timedelta

from photo_assistant.domain.grouping import Shot, group_shots, phash_distance

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
