"""Events (FEATURES 5.6): the library split into trips, birthdays and days out, by capture
time, place and the people on the photos, each named from facts alone."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.domain.events import (
    MIN_PHOTOS,
    MOVED_KM,
    OVERNIGHT_GAP,
    SAME_EVENT_GAP,
    SAME_PEOPLE_GAP,
    EventPhoto,
    album_events,
    distance_km,
    event_title,
    split_events,
)
from photo_assistant.domain.places import Place

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
SECOND = timedelta(seconds=1)

# Home is Rennes; Saint-Malo is ~65 km north, Vannes ~100 km south-west.
RENNES = (48.1173, -1.6778)
SAINT_MALO = (48.6493, -2.0257)
VANNES = (47.6582, -2.7608)
RENNES_PLACE = Place("France", "Brittany", "Rennes")
SAINT_MALO_PLACE = Place("France", "Brittany", "Saint-Malo")
VANNES_PLACE = Place("France", "Brittany", "Vannes")

_next_id = iter(range(1, 1_000_000))


def photo(
    at: datetime | None,
    where: tuple[float, float] | None = RENNES,
    *,
    people: frozenset[int] = frozenset(),
    place: Place | None = None,
) -> EventPhoto:
    return EventPhoto(next(_next_id), at, where, people, place)


def run(
    start: datetime,
    n: int,
    where: tuple[float, float] | None = RENNES,
    *,
    every: timedelta = 10 * MINUTE,
    people: frozenset[int] = frozenset(),
    place: Place | None = None,
) -> list[EventPhoto]:
    return [photo(start + i * every, where, people=people, place=place) for i in range(n)]


def proposed(photos: list[EventPhoto]) -> list[str]:
    """The titles proposed for these photos, taken while living at home in Rennes."""
    return [event_title(e) for e in album_events(HOME_LIFE + photos)]


def ids(photos: list[EventPhoto]) -> list[int]:
    return [p.asset_id for p in photos]


def groups(photos: list[EventPhoto]) -> list[list[int]]:
    return [[p.asset_id for p in e.photos] for e in split_events(photos)]


# A life at home: a few photos a week in Rennes all through 2024, so Rennes is home.
HOME_LIFE = [
    p for week in range(52) for p in run(datetime(2024, 1, 1, 18) + week * 7 * DAY, 3, RENNES)
]
JULY = datetime(2025, 7, 12, 10)


# --- distance ------------------------------------------------------------------------------


def test_distance_is_the_great_circle_in_kilometres() -> None:
    assert distance_km(RENNES, RENNES) == 0
    assert distance_km(RENNES, SAINT_MALO) == pytest.approx(65, abs=3)
    assert distance_km(RENNES, VANNES) == distance_km(VANNES, RENNES)


# --- time gaps -----------------------------------------------------------------------------


def test_photos_close_in_time_at_one_place_are_one_event() -> None:
    party = run(JULY, 12)
    assert groups(party) == [ids(party)]


def test_a_gap_exactly_at_the_threshold_keeps_one_event() -> None:
    a, b = photo(JULY), photo(JULY + SAME_EVENT_GAP)
    assert groups([a, b]) == [[a.asset_id, b.asset_id]]


def test_a_gap_just_past_the_threshold_splits() -> None:
    a, b = photo(JULY), photo(JULY + SAME_EVENT_GAP + SECOND)
    assert groups([a, b]) == [[a.asset_id], [b.asset_id]]


def test_events_come_oldest_first_and_photos_in_time_order() -> None:
    later, earlier = run(JULY + DAY, 3), run(JULY, 3)
    shuffled = [later[2], earlier[1], later[0], earlier[0], later[1], earlier[2]]
    assert groups(shuffled) == [ids(earlier), ids(later)]


def test_two_days_at_home_are_two_events() -> None:
    saturday = run(datetime(2025, 3, 8, 14), 10)
    sunday = run(datetime(2025, 3, 9, 10), 10)
    assert groups(HOME_LIFE + saturday + sunday)[-2:] == [ids(saturday), ids(sunday)]


# --- photos without a date, a place, or with only one --------------------------------------


def test_photos_with_no_date_belong_to_no_event() -> None:
    dated = run(JULY, 3)
    assert groups([photo(None), *dated, photo(None)]) == [ids(dated)]
    assert split_events([photo(None)]) == []


def test_an_empty_library_has_no_event() -> None:
    assert split_events([]) == []
    assert album_events([]) == []


def test_a_single_photo_is_an_event_of_one_too_small_for_an_album() -> None:
    alone = photo(JULY)
    (event,) = split_events([alone])
    assert ids(list(event.photos)) == [alone.asset_id]
    assert album_events([alone]) == []


def test_photos_without_gps_group_by_time_alone() -> None:
    party = run(JULY, 6, None)
    assert groups(party) == [ids(party)]
    a, b = photo(JULY, None), photo(JULY + SAME_EVENT_GAP + SECOND, None)
    assert groups([a, b]) == [[a.asset_id], [b.asset_id]]


def test_a_photo_without_gps_inside_an_event_does_not_split_it() -> None:
    before, after = run(JULY, 3, SAINT_MALO), run(JULY + HOUR, 3, SAINT_MALO)
    lost = photo(JULY + 40 * MINUTE, None)
    assert groups([*before, lost, *after]) == [[*ids(before), lost.asset_id, *ids(after)]]


# --- place ---------------------------------------------------------------------------------


def test_two_events_on_the_same_day_in_different_places_are_two_events() -> None:
    beach = run(datetime(2025, 7, 12, 10), 10, SAINT_MALO)
    party = run(datetime(2025, 7, 12, 12), 10, RENNES)  # an hour after the beach ended
    found = groups(HOME_LIFE + beach + party)
    assert found[-2:] == [ids(beach), ids(party)]


def test_moving_just_under_the_distance_threshold_is_the_same_event() -> None:
    near = (RENNES[0] + (MOVED_KM - 1) / 111.2, RENNES[1])  # a degree of latitude ≈ 111.2 km
    a, b = photo(JULY), photo(JULY + HOUR, near)
    assert distance_km(RENNES, near) < MOVED_KM
    assert groups([a, b]) == [[a.asset_id, b.asset_id]]


def test_a_day_out_with_two_stops_away_from_home_is_one_event() -> None:
    morning = run(datetime(2025, 7, 12, 10), 6, SAINT_MALO)
    afternoon = run(datetime(2025, 7, 12, 14), 6, VANNES)
    assert groups(HOME_LIFE + morning + afternoon)[-1] == ids(morning) + ids(afternoon)


# --- trips over several days ---------------------------------------------------------------


def test_a_multi_day_trip_crossing_midnight_is_one_event() -> None:
    trip = [
        p
        for day in range(4)  # four days in Saint-Malo, 9:00 to 21:00
        for p in run(datetime(2025, 7, 12, 9) + day * DAY, 13, SAINT_MALO, every=HOUR)
    ]
    trip.append(photo(datetime(2025, 7, 15, 23, 50), SAINT_MALO))
    trip.append(photo(datetime(2025, 7, 16, 0, 10), SAINT_MALO))  # just after midnight
    assert groups(HOME_LIFE + trip)[-1] == ids(sorted(trip, key=lambda p: p.taken_at or JULY))


def test_a_night_longer_than_the_overnight_gap_ends_the_trip() -> None:
    first = run(JULY, 4, SAINT_MALO)
    last = first[-1].taken_at
    assert last is not None
    second = run(last + OVERNIGHT_GAP + SECOND, 4, SAINT_MALO)
    assert groups(HOME_LIFE + first + second)[-2:] == [ids(first), ids(second)]


def test_the_night_at_home_is_not_bridged() -> None:
    evening = run(datetime(2025, 7, 12, 18), 4)
    morning = run(datetime(2025, 7, 13, 9), 4)
    assert groups(HOME_LIFE + evening + morning)[-2:] == [ids(evening), ids(morning)]


def test_without_any_gps_there_is_no_home_and_no_trip_over_night() -> None:
    evening = run(datetime(2025, 7, 12, 18), 4, None)
    morning = run(datetime(2025, 7, 13, 9), 4, None)
    assert groups(evening + morning) == [ids(evening), ids(morning)]


# --- people as the tie-breaker -------------------------------------------------------------


def test_the_same_people_a_few_hours_later_are_the_same_event() -> None:
    sam = frozenset({7})
    lunch = run(datetime(2025, 3, 8, 12), 5, people=sam)
    cake = run(datetime(2025, 3, 8, 12, 40) + SAME_EVENT_GAP + HOUR, 5, people=sam | {9})
    assert groups(lunch + cake) == [ids(lunch) + ids(cake)]


def test_other_people_a_few_hours_later_are_another_event() -> None:
    lunch = run(datetime(2025, 3, 8, 12), 5, people=frozenset({7}))
    cake = run(datetime(2025, 3, 8, 12, 40) + SAME_EVENT_GAP + HOUR, 5, people=frozenset({9}))
    assert groups(lunch + cake) == [ids(lunch), ids(cake)]


def test_shared_people_never_bridge_more_than_the_people_gap() -> None:
    sam = frozenset({7})
    a = photo(JULY, people=sam)
    b = photo(JULY + SAME_PEOPLE_GAP + SECOND, people=sam)
    assert groups([a, b]) == [[a.asset_id], [b.asset_id]]
    c = photo(JULY + SAME_PEOPLE_GAP, people=sam)
    assert groups([a, c]) == [[a.asset_id, c.asset_id]]


def test_shared_people_do_not_glue_two_places() -> None:
    sam = frozenset({7})
    beach = run(datetime(2025, 7, 12, 10), 5, SAINT_MALO, people=sam)
    home = run(datetime(2025, 7, 12, 12), 5, RENNES, people=sam)
    assert groups(HOME_LIFE + beach + home)[-2:] == [ids(beach), ids(home)]


# --- which events become album proposals ---------------------------------------------------


def test_only_events_with_enough_photos_are_proposed() -> None:
    small = run(datetime(2025, 3, 8, 12), MIN_PHOTOS - 1)
    enough = run(datetime(2025, 4, 8, 12), MIN_PHOTOS)
    assert [ids(list(e.photos)) for e in album_events(small + enough)] == [ids(enough)]


def test_an_event_has_its_days_count_and_a_key_that_new_photos_do_not_change() -> None:
    trip = run(datetime(2025, 7, 12, 20), 10, SAINT_MALO, every=HOUR)
    (event,) = album_events(trip)
    assert (event.first_day.isoformat(), event.last_day.isoformat()) == ("2025-07-12", "2025-07-13")
    assert event.count == 10
    later = photo(datetime(2025, 7, 13, 7), SAINT_MALO)
    (grown,) = album_events([*trip, later])
    assert grown.count == 11
    assert grown.key == event.key


# --- titles: facts only --------------------------------------------------------------------


def test_a_trip_through_one_region_is_named_after_it_and_its_month() -> None:
    malo = run(datetime(2025, 7, 12, 10), 6, SAINT_MALO, every=2 * HOUR, place=SAINT_MALO_PLACE)
    vannes = run(datetime(2025, 7, 13, 10), 6, VANNES, every=2 * HOUR, place=VANNES_PLACE)
    assert proposed(malo + vannes) == ["Brittany · July 2025"]


def test_one_city_names_the_event() -> None:
    trip = run(datetime(2025, 7, 12, 10), 10, SAINT_MALO, every=4 * HOUR, place=SAINT_MALO_PLACE)
    assert proposed(trip) == ["Saint-Malo · July 2025"]


def test_a_single_day_is_named_by_its_date() -> None:
    party = run(datetime(2025, 3, 8, 14), 10, place=RENNES_PLACE)
    assert proposed(party) == ["Rennes · 8 March 2025"]


def test_a_trip_across_two_months_names_both() -> None:
    trip = run(datetime(2025, 7, 31, 10), 10, SAINT_MALO, every=4 * HOUR, place=SAINT_MALO_PLACE)
    assert proposed(trip) == ["Saint-Malo · July and August 2025"]


def test_without_a_place_name_the_title_is_the_date_alone() -> None:
    (event,) = album_events(run(datetime(2025, 3, 8, 14), 10, None))
    assert event_title(event) == "8 March 2025"


def test_two_countries_name_the_city_with_the_most_photos() -> None:
    lisbon = Place("Portugal", "Lisboa", "Lisbon")
    porto = Place("Portugal", "Porto", "Porto")
    madrid = Place("Spain", "Madrid", "Madrid")
    trip = (
        run(datetime(2025, 7, 12, 10), 3, (38.72, -9.14), place=lisbon)
        + run(datetime(2025, 7, 12, 11), 4, (41.15, -8.61), place=porto)
        + run(datetime(2025, 7, 12, 12), 2, (40.42, -3.70), place=madrid)
    )
    assert proposed(trip) == ["Porto · 12 July 2025"]
