"""Memories on Home (issue 54): trips away from home and months at home, named in English."""

from datetime import date, datetime, timedelta

import pytest

from photo_assistant.domain.memories import (
    MAX_MEMORIES,
    Moment,
    cover_of,
    home_place,
    memories,
    period_words,
    trip_title,
    trips,
)

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
TODAY = date(2026, 10, 14)


def shots(
    start: datetime, n: int, *, place: str | None = None, first_id: int = 1, every: timedelta = HOUR
) -> list[Moment]:
    return [Moment(first_id + i, start + i * every, place) for i in range(n)]


# Home life: 100 photos in Paris, one every two days in 2019 (16 a month at most: no month of
# memories), so Paris is home and the trips below are away from it.
HOME = "Paris"
BASE = shots(datetime(2019, 1, 1, 10), 100, place=HOME, first_id=10_000, every=2 * DAY)
JULY = datetime(2024, 7, 1, 10)


def away(
    n: int, *, first_id: int = 1, start: datetime = JULY, every: timedelta = HOUR
) -> list[Moment]:
    return shots(start, n, place="Lisbon", first_id=first_id, every=every)


# --- home: the city with the most photos ----------------------------------------------------


def test_home_is_the_city_with_the_most_photos() -> None:
    assert home_place(BASE + away(30)) == HOME
    rome, oslo = shots(JULY, 3, place="Rome"), shots(JULY + DAY, 3, place="Oslo", first_id=9)
    assert home_place(oslo + rome) == "Rome", "a tie: the city seen first"
    assert home_place(shots(JULY, 5)) is None


def test_photos_at_home_make_no_trip() -> None:
    assert trips(BASE) == []


# --- trips: away, split on a gap of more than two days or a change of city, 21 days at most -----


def test_photos_exactly_two_days_apart_stay_one_trip() -> None:
    before = away(10)
    after = away(10, first_id=100, start=before[-1].taken_at + 2 * DAY)
    assert [len(t) for t in trips(BASE + before + after)] == [20]


def test_a_gap_of_more_than_two_days_starts_a_new_trip() -> None:
    before = away(10)
    after = away(10, first_id=100, start=before[-1].taken_at + 2 * DAY + timedelta(seconds=1))
    assert [t[0].asset_id for t in trips(BASE + before + after)] == [1, 100]


def test_a_change_of_city_within_two_days_starts_a_new_trip() -> None:
    lisbon = away(10)
    porto = shots(lisbon[-1].taken_at + HOUR, 10, place="Porto", first_id=100)
    found = trips(BASE + lisbon + porto)
    assert [(t[0].place, len(t)) for t in found] == [("Lisbon", 10), ("Porto", 10)]


def test_a_trip_lasts_21_days_at_most() -> None:
    three_weeks = away(22, every=DAY)  # day 0 to day 21
    assert [len(t) for t in trips(BASE + three_weeks)] == [22]
    a_month = away(61, every=12 * HOUR)  # 30 days: 21 days, then the rest
    assert [len(t) for t in trips(BASE + a_month)] == [43, 18]


def test_nine_photos_are_a_day_out_and_ten_are_a_trip() -> None:
    nine = away(9)
    ten = away(10, first_id=100, start=JULY + 30 * DAY)
    assert [len(t) for t in trips(BASE + nine + ten)] == [10]


def test_trips_come_oldest_first_whatever_order_the_photos_come_in() -> None:
    spring = away(10, start=datetime(2024, 3, 1, 10))
    summer = away(10, first_id=100)
    found = trips(list(reversed(BASE + summer + spring)))
    assert [[m.asset_id for m in t] for t in found] == [
        [m.asset_id for m in spring],
        [m.asset_id for m in summer],
    ]


def test_photos_without_a_place_go_with_the_nearest_photo_that_has_one() -> None:
    lisbon = away(5) + shots(JULY + 5 * HOUR, 5, first_id=50)
    assert [len(t) for t in trips(BASE + lisbon)] == [10]


def test_a_photo_without_a_place_counts_as_home_when_its_neighbour_is_unclear() -> None:
    lisbon = away(10)  # 10:00 to 19:00
    halfway = shots(JULY + 10 * HOUR, 1, first_id=50)  # an hour after Lisbon, an hour before Paris
    paris = shots(JULY + 11 * HOUR, 1, place=HOME, first_id=60)
    far = shots(JULY + 9 * HOUR + 2 * DAY + HOUR, 1, first_id=70)  # over two days from any
    assert [len(t) for t in trips(BASE + lisbon + halfway + paris)] == [10]
    assert [len(t) for t in trips(BASE + lisbon + far)] == [10]


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
    """Home life, then ``count`` trips of ten photos, a month apart, the first in January 2020."""
    found = list(BASE)
    for n in range(count):
        start = datetime(2020 + n // 12, n % 12 + 1, 3, 10)
        found += shots(start, 10, place=f"Place {n}", first_id=100 * n + 1)
    return found


def test_a_memory_says_its_title_days_count_cover_and_key() -> None:
    trip = away(10, start=datetime(2024, 7, 3, 22), every=6 * HOUR)
    (memory,) = memories(BASE + trip, TODAY)
    assert memory.title == "Lisbon, July 2024"
    assert (memory.first_day, memory.last_day) == (date(2024, 7, 3), date(2024, 7, 6))
    assert (memory.count, memory.cover_id, memory.key) == (10, 1, "2024-07-03_2024-07-06")


def test_a_month_at_home_needs_twenty_photos_at_home() -> None:
    october = datetime(2024, 10, 1, 10)
    nineteen = shots(october, 19, place=HOME, first_id=1, every=DAY)
    assert memories(BASE + nineteen, TODAY) == []
    twenty = shots(october, 20, place=HOME, first_id=1, every=DAY)
    (month,) = memories(BASE + twenty, TODAY)
    assert (month.title, month.count, month.cover_id) == ("October 2024", 20, 1)
    assert (month.first_day, month.last_day) == (date(2024, 10, 1), date(2024, 10, 31))
    assert month.key == "2024-10-01_2024-10-31"


def test_a_month_at_home_counts_the_whole_month_and_keeps_its_cover_at_home() -> None:
    october = datetime(2024, 10, 1, 10)
    at_home = shots(october, 20, place=HOME, first_id=1, every=DAY)
    lisbon = [Moment(100, datetime(2024, 10, 25, 9), "Lisbon", True)]
    lisbon += away(9, first_id=101, start=datetime(2024, 10, 25, 10))
    month, trip = memories(BASE + at_home + lisbon, TODAY)
    assert (month.title, month.count, month.cover_id) == ("October 2024", 30, 1)
    assert (trip.title, trip.count, trip.cover_id) == ("Lisbon, October 2024", 10, 100)


def test_a_library_without_places_is_all_home() -> None:
    (month,) = memories(shots(datetime(2024, 10, 1, 10), 20, every=DAY), TODAY)
    assert month.title == "October 2024"


def test_the_two_newest_memories_come_first_and_the_rest_rotate_daily() -> None:
    library = _year_of_trips(14)
    shown = memories(library, TODAY)
    assert len(shown) == MAX_MEMORIES
    newest = [m.first_day for m in shown[:2]]
    assert newest == [date(2021, 2, 3), date(2021, 1, 3)]
    assert memories(library, TODAY) == shown, "the same day, the same memories"
    tomorrow = memories(library, TODAY + DAY)
    assert [m.first_day for m in tomorrow[:2]] == newest
    assert tomorrow[2:] != shown[2:]
    seen = {m.key for d in range(3) for m in memories(library, TODAY + d * DAY)}
    assert len(seen) == 14, "a few days show every memory"


def test_a_few_memories_are_all_shown_in_a_daily_order() -> None:
    library = _year_of_trips(5)
    shown, tomorrow = memories(library, TODAY), memories(library, TODAY + DAY)
    assert len(shown) == 5 and {m.key for m in shown} == {m.key for m in tomorrow}
    assert shown[:2] == tomorrow[:2] and shown[2:] != tomorrow[2:]


def test_no_trips_no_memories() -> None:
    assert memories(shots(datetime(2024, 7, 3), 9), TODAY) == []
