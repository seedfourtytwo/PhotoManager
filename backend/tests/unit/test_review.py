"""Which photos wait for a person's decision instead of joining the library."""

import random
from datetime import datetime, timedelta

import pytest

from photo_assistant.domain import review
from photo_assistant.domain.grouping import NEAR_DUPLICATE_WINDOW, Shot
from photo_assistant.domain.review import MAX_LOOKALIKE_DISTANCE, clutter_reason, lookalikes
from photo_assistant.domain.tags import TagScore

NOON = datetime(2024, 5, 1, 12, 0, 0)


def bits(n: int) -> str:
    """A hash with the lowest ``n`` bits set."""
    return f"{(1 << n) - 1:016x}"


def shots(hashes: dict[int, str], taken: dict[int, datetime] | None = None) -> list[Shot]:
    """Each photo on a day of its own unless ``taken`` says when."""
    taken = taken or {}
    return [
        Shot(i, taken.get(i, NOON + timedelta(days=i)), "iPhone", phash)
        for i, phash in hashes.items()
    ]


def test_a_new_photo_close_to_a_library_photo_is_a_lookalike() -> None:
    library = {1: bits(0), 2: "ffffffffffffffff"}
    new = {10: bits(MAX_LOOKALIKE_DISTANCE), 11: bits(MAX_LOOKALIKE_DISTANCE + 1), 12: bits(64)}
    assert lookalikes(shots(new), shots(library)) == {10: 1, 12: 2}


def test_the_closest_library_photo_is_named_and_ties_go_to_the_oldest() -> None:
    library = shots({3: bits(0), 4: bits(1), 5: bits(3)})
    assert lookalikes(shots({10: bits(2)}), library) == {10: 4}
    assert lookalikes(shots({10: bits(0)}), shots({7: bits(0), 6: bits(0)})) == {10: 6}


def test_new_photos_are_never_compared_with_each_other_and_empty_is_fine() -> None:
    assert lookalikes(shots({10: bits(0), 11: bits(0)}), []) == {}
    assert lookalikes([], shots({1: bits(0)})) == {}


def test_a_photo_without_a_hash_resembles_nothing() -> None:
    hashed, bare = Shot(1, NOON, None, bits(0)), Shot(2, NOON + timedelta(days=1), None, None)
    assert lookalikes([bare], [hashed]) == {}
    assert lookalikes([hashed], [bare]) == {}


@pytest.mark.parametrize("apart", [timedelta(0), timedelta(seconds=1), NEAR_DUPLICATE_WINDOW])
def test_a_library_photo_taken_within_the_grouping_window_is_a_sibling_not_a_lookalike(
    apart: timedelta,
) -> None:
    """Two frames of one burst hashed by two jobs: grouping joins them, review leaves them."""
    for when in (NOON - apart, NOON + apart):
        assert lookalikes(shots({10: bits(0)}, {10: NOON}), shots({1: bits(1)}, {1: when})) == {}


def test_just_outside_the_grouping_window_it_is_a_lookalike_again() -> None:
    apart = NEAR_DUPLICATE_WINDOW + timedelta(seconds=1)
    for when in (NOON - apart, NOON + apart):
        found = lookalikes(shots({10: bits(0)}, {10: NOON}), shots({1: bits(1)}, {1: when}))
        assert found == {10: 1}


def test_a_sibling_does_not_hide_an_older_copy_elsewhere_in_the_library() -> None:
    library = shots(
        {1: bits(2), 2: bits(0), 3: bits(0), 4: bits(0)},
        {2: NOON - timedelta(seconds=2), 3: NOON + timedelta(minutes=3)},
    )
    assert lookalikes(shots({10: bits(0)}, {10: NOON}), library) == {10: 4}
    assert lookalikes(shots({10: bits(0)}, {10: NOON}), library[:3]) == {10: 1}


def compare_with_every_library_photo(new: list[Shot], library: list[Shot]) -> dict[int, int]:
    """The oracle: ``lookalikes`` as it was (every new photo against the whole library), plus
    the rule that a library photo within the grouping window does not count."""
    known = sorted((s.asset_id, int(s.phash or "0", 16), s.taken_at) for s in library)
    found: dict[int, int] = {}
    for shot in new:
        mine = int(shot.phash or "0", 16)
        best, best_distance = None, MAX_LOOKALIKE_DISTANCE + 1
        for other_id, other, taken_at in known:
            if abs(taken_at - shot.taken_at) <= NEAR_DUPLICATE_WINDOW:
                continue
            distance = (mine ^ other).bit_count()
            if distance < best_distance:
                best, best_distance = other_id, distance
        if best is not None:
            found[shot.asset_id] = best
    return found


def random_shots(rng: random.Random, n: int, first_id: int, hours: int) -> list[Shot]:
    """Hashes a few bits from a handful of pictures (many equal), times bunched in bursts."""
    pictures = [rng.getrandbits(64) for _ in range(max(2, n // 6))]
    found = []
    for k in range(n):
        phash = rng.choice(pictures)
        for _ in range(rng.choice((0, 0, 0, 1, 1, 2, 9))):
            phash ^= 1 << rng.randrange(64)
        at = NOON + timedelta(
            hours=rng.randrange(hours), seconds=rng.choice((0, 1, 300, 599, 600, 601))
        )
        found.append(Shot(first_id + k, at, None, f"{phash:016x}"))
    rng.shuffle(found)
    return found


@pytest.mark.parametrize("seed", range(30))
def test_lookalikes_agree_with_comparing_every_new_photo_with_every_library_photo(
    seed: int,
) -> None:
    rng = random.Random(seed)
    pool = random_shots(rng, 240, first_id=1, hours=rng.choice((1, 3, 50)))
    library, new = pool[:160], pool[160:]
    expected = compare_with_every_library_photo(new, library)
    assert lookalikes(new, library) == expected
    assert 3 <= len(expected) < len(new), "some photos are look-alikes and some are not"


def test_a_new_photo_is_compared_only_with_library_hashes_that_share_a_band_of_bits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It was every new photo against the whole library: 20k new x 30k = 6e8 comparisons."""
    rng = random.Random(1)
    library = [
        Shot(i, NOON + timedelta(days=i), None, f"{rng.getrandbits(64):016x}") for i in range(3000)
    ]
    new = [
        Shot(
            10_000 + i,
            NOON - timedelta(days=i + 1),
            None,
            f"{int(s.phash or '', 16) ^ (1 << i % 64):016x}",
        )
        for i, s in enumerate(library[:600])
    ]
    compared = []
    distance = review._distance

    def counted(a: int, b: int) -> int:
        compared.append(1)
        return distance(a, b)

    monkeypatch.setattr(review, "_distance", counted)
    found = lookalikes(new, library)
    assert found == {10_000 + i: i for i in range(600)}
    assert len(compared) < len(new) * len(library) / 100


def test_clutter_is_named_only_when_it_is_the_best_guess() -> None:
    assert clutter_reason([TagScore("receipt", 0.09), TagScore("food", 0.04)]) == "receipt"
    assert clutter_reason([TagScore("food", 0.09), TagScore("receipt", 0.04)]) is None
    assert clutter_reason([TagScore("beach", 0.1)]) is None
    assert clutter_reason([]) is None
