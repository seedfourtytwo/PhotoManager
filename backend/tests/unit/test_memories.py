"""Memories on Home (issue 54): trips found from capture times, named in plain English."""

from datetime import date, datetime, timedelta

import pytest

from photo_assistant.domain.memories import (
    MAX_MEMORIES,
    Moment,
    cover_of,
    memories,
    period_words,
    trip_title,
    trips,
)

HOUR = timedelta(hours=1)


def shots(
    start: datetime, n: int, *, place: str | None = None, first_id: int = 1, every: timedelta = HOUR
) -> list[Moment]:
    return [Moment(first_id + i, start + i * every, place) for i in range(n)]


# --- trips: split where photos are more than two days apart; at least ten photos ---------------


def test_photos_exactly_two_days_apart_stay_one_trip() -> None:
    before = shots(datetime(2024, 7, 1, 10), 10)
    after = shots(before[-1].taken_at + timedelta(days=2), 10, first_id=100)
    assert [len(t) for t in trips(before + after)] == [20]


def test_a_gap_of_more_than_two_days_starts_a_new_trip() -> None:
    before = shots(datetime(2024, 7, 1, 10), 10)
    after = shots(before[-1].taken_at + timedelta(days=2, seconds=1), 10, first_id=100)
    assert [[m.asset_id for m in t][:1] for t in trips(before + after)] == [[1], [100]]


def test_nine_photos_are_a_day_out_and_ten_are_a_trip() -> None:
    nine = shots(datetime(2024, 3, 1, 10), 9)
    ten = shots(datetime(2024, 5, 1, 10), 10, first_id=100)
    assert [len(t) for t in trips(nine + ten)] == [10]


def test_trips_come_oldest_first_whatever_order_the_photos_come_in() -> None:
    spring = shots(datetime(2024, 3, 1, 10), 10)
    summer = shots(datetime(2024, 7, 1, 10), 10, first_id=100)
    found = trips(list(reversed(summer + spring)))
    assert [[m.asset_id for m in t] for t in found] == [
        [m.asset_id for m in spring],
        [m.asset_id for m in summer],
    ]


def test_no_photos_no_trips() -> None:
    assert trips([]) == []


# --- titles -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "last", "words"),
    [
        (date(2024, 7, 3), date(2024, 7, 10), "July 2024"),
        (date(2024, 7, 28), date(2024, 8, 4), "July and August 2024"),
        (date(2024, 7, 28), date(2024, 9, 2), "July to September 2024"),
        (date(2023, 12, 28), date(2024, 1, 3), "December 2023 and January 2024"),
        (date(2023, 11, 28), date(2024, 1, 3), "November 2023 to January 2024"),
        (date(2023, 7, 1), date(2024, 7, 1), "July 2023 to July 2024"),
    ],
)
def test_the_period_in_plain_words(first: date, last: date, words: str) -> None:
    assert period_words(first, last) == words


def test_a_trip_is_titled_after_its_main_place_and_its_months() -> None:
    start = datetime(2024, 7, 30, 10)
    daily = timedelta(days=1)
    trip = shots(start, 6, place="Lisbon") + shots(
        start + 6 * HOUR, 4, place="Sintra", first_id=10, every=daily
    )
    assert trip_title(trip) == "Lisbon, July and August 2024"


def test_a_trip_without_a_place_is_titled_by_its_months_alone() -> None:
    assert trip_title(shots(datetime(2024, 7, 3, 10), 10)) == "July 2024"


def test_photos_without_a_place_do_not_outvote_the_place() -> None:
    start = datetime(2024, 7, 3, 10)
    trip = shots(start, 7) + shots(start + 7 * HOUR, 3, place="Porto", first_id=50)
    assert trip_title(trip) == "Porto, July 2024"


def test_a_tie_between_places_goes_to_the_one_seen_first() -> None:
    start = datetime(2024, 7, 3, 10)
    trip = shots(start, 5, place="Sintra") + shots(start + 5 * HOUR, 5, place="Lisbon", first_id=9)
    assert trip_title(trip) == "Sintra, July 2024"
    assert trip_title(list(reversed(trip))) == "Sintra, July 2024", "by time, not by input order"


# --- covers -----------------------------------------------------------------------------------


def test_the_cover_is_the_first_favourite_else_the_first_photo() -> None:
    start = datetime(2024, 7, 3, 10)
    plain = shots(start, 4, first_id=10)
    assert cover_of(list(reversed(plain))) == 10
    loved = [*plain[:2], Moment(20, start + 2 * HOUR, None, True), Moment(21, start, None, True)]
    assert cover_of(loved) == 21


# --- the memories Home lists ------------------------------------------------------------------


def _year_of_trips(count: int) -> list[Moment]:
    """``count`` trips of ten photos, a month apart, the first in January 2020."""
    found: list[Moment] = []
    for n in range(count):
        start = datetime(2020 + n // 12, n % 12 + 1, 3, 10)
        found += shots(start, 10, place=f"Place {n}", first_id=100 * n + 1)
    return found


def test_a_memory_says_its_title_days_count_cover_and_key() -> None:
    start = datetime(2024, 7, 3, 22)
    trip = shots(start, 10, place="Lisbon", every=6 * HOUR)
    (memory,) = memories(trip, date(2026, 10, 14))
    assert memory.title == "Lisbon, July 2024"
    assert (memory.first_day, memory.last_day) == (date(2024, 7, 3), date(2024, 7, 6))
    assert (memory.count, memory.cover_id, memory.key) == (10, 1, "2024-07-03_2024-07-06")


def test_the_two_newest_memories_come_first_and_the_rest_rotate_daily() -> None:
    library = _year_of_trips(14)
    today = date(2026, 10, 14)
    shown = memories(library, today)
    assert len(shown) == MAX_MEMORIES
    newest = [m.first_day for m in shown[:2]]
    assert newest == [date(2021, 2, 3), date(2021, 1, 3)]
    assert memories(library, today) == shown, "the same day, the same memories"
    tomorrow = memories(library, today + timedelta(days=1))
    assert [m.first_day for m in tomorrow[:2]] == newest
    assert tomorrow[2:] != shown[2:]
    seen = {m.key for d in range(3) for m in memories(library, today + timedelta(days=d))}
    assert len(seen) == 14, "a few days show every memory"


def test_a_few_memories_are_all_shown_in_a_daily_order() -> None:
    library = _year_of_trips(5)
    today = date(2026, 10, 14)
    shown, tomorrow = memories(library, today), memories(library, today + timedelta(days=1))
    assert len(shown) == 5 and {m.key for m in shown} == {m.key for m in tomorrow}
    assert shown[:2] == tomorrow[:2] and shown[2:] != tomorrow[2:]


def test_no_trips_no_memories() -> None:
    assert memories(shots(datetime(2024, 7, 3), 9), date(2026, 10, 14)) == []
