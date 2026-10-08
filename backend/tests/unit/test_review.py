"""Which photos wait for a person's decision instead of joining the library."""

from photo_assistant.domain.review import MAX_LOOKALIKE_DISTANCE, clutter_reason, lookalikes
from photo_assistant.domain.tags import TagScore


def bits(n: int) -> str:
    """A hash with the lowest ``n`` bits set."""
    return f"{(1 << n) - 1:016x}"


def test_a_new_photo_close_to_a_library_photo_is_a_lookalike() -> None:
    library = {1: bits(0), 2: "ffffffffffffffff"}
    new = {10: bits(MAX_LOOKALIKE_DISTANCE), 11: bits(MAX_LOOKALIKE_DISTANCE + 1), 12: bits(64)}
    assert lookalikes(new, library) == {10: 1, 12: 2}


def test_the_closest_library_photo_is_named_and_ties_go_to_the_oldest() -> None:
    assert lookalikes({10: bits(2)}, {3: bits(0), 4: bits(1), 5: bits(3)}) == {10: 4}
    assert lookalikes({10: bits(0)}, {7: bits(0), 6: bits(0)}) == {10: 6}


def test_new_photos_are_never_compared_with_each_other_and_empty_is_fine() -> None:
    assert lookalikes({10: bits(0), 11: bits(0)}, {}) == {}
    assert lookalikes({}, {1: bits(0)}) == {}


def test_clutter_is_named_only_when_it_is_the_best_guess() -> None:
    assert clutter_reason([TagScore("receipt", 0.09), TagScore("food", 0.04)]) == "receipt"
    assert clutter_reason([TagScore("food", 0.09), TagScore("receipt", 0.04)]) is None
    assert clutter_reason([TagScore("beach", 0.1)]) is None
    assert clutter_reason([]) is None
