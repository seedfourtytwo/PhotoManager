"""On this day (Home, issue 54): the photos of today's date in an earlier year."""

from datetime import date, datetime, timedelta

from photo_assistant.domain.memories import Moment
from photo_assistant.domain.on_this_day import anniversary, on_this_day

TODAY = date(2026, 10, 14)


def on(day: date, n: int, *, first_id: int = 1, place: str | None = None) -> list[Moment]:
    noon = datetime(day.year, day.month, day.day, 12)
    return [Moment(first_id + i, noon + timedelta(minutes=i), place) for i in range(n)]


def test_nothing_from_an_earlier_year_is_nothing() -> None:
    assert on_this_day([], TODAY) is None
    assert on_this_day(on(TODAY, 3) + on(date(2026, 10, 12), 3, first_id=9), TODAY) is None


def test_the_year_with_most_photos_on_the_day_is_picked() -> None:
    photos = (
        on(date(2019, 10, 14), 2)
        + on(date(2023, 10, 14), 3, first_id=10)
        + on(date(2023, 10, 15), 5, first_id=20)
        + on(date(2021, 10, 13), 9, first_id=30)
    )
    found = on_this_day(photos, TODAY)
    assert found is not None and found.exact
    assert (found.day, found.years_ago, found.count) == (date(2023, 10, 14), 3, 3)
    assert (found.first_day, found.last_day) == (date(2023, 10, 14), date(2023, 10, 14))
    assert [m.asset_id for m in found.photos] == [10, 11, 12]


def test_a_tie_goes_to_the_most_recent_year() -> None:
    photos = on(date(2019, 10, 14), 2) + on(date(2022, 10, 14), 2, first_id=10)
    found = on_this_day(photos, TODAY)
    assert found is not None and (found.day, found.years_ago) == (date(2022, 10, 14), 4)


def test_without_photos_on_the_day_three_days_either_side_count() -> None:
    photos = (
        on(date(2020, 10, 11), 2)
        + on(date(2020, 10, 17), 1, first_id=10)
        + on(date(2021, 10, 18), 5, first_id=20)
        + on(date(2022, 10, 10), 5, first_id=30)
    )
    found = on_this_day(photos, TODAY)
    assert found is not None and not found.exact
    assert (found.day, found.years_ago, found.count) == (date(2020, 10, 14), 6, 3)
    assert (found.first_day, found.last_day) == (date(2020, 10, 11), date(2020, 10, 17))


def test_the_days_around_new_year_reach_into_the_year_before() -> None:
    today = date(2027, 1, 1)
    found = on_this_day(on(date(2025, 12, 30), 4), today)
    assert found is not None and not found.exact
    assert (found.day, found.years_ago) == (date(2026, 1, 1), 1)
    assert (found.first_day, found.last_day) == (date(2025, 12, 29), date(2026, 1, 4))


def test_29_february_is_28_february_in_the_other_years() -> None:
    assert anniversary(date(2028, 2, 29), 2027) == date(2027, 2, 28)
    assert anniversary(date(2028, 2, 29), 2024) == date(2024, 2, 29)
    leap_day = on_this_day(on(date(2027, 2, 28), 2), date(2028, 2, 29))
    assert leap_day is not None and leap_day.exact and leap_day.day == date(2027, 2, 28)
    common = on_this_day(on(date(2024, 2, 29), 2), date(2027, 2, 28))
    assert common is not None and not common.exact and common.day == date(2024, 2, 28)


def test_the_cover_is_a_favourite_and_the_place_the_main_one() -> None:
    day = date(2023, 10, 14)
    loved = Moment(50, datetime(2023, 10, 14, 18), "Sintra", favourite=True)
    photos = [*on(day, 3, place="Lisbon"), loved]
    found = on_this_day(photos, TODAY)
    assert found is not None and (found.cover_id, found.place) == (50, "Lisbon")
    plain = on_this_day(on(day, 3, first_id=7), TODAY)
    assert plain is not None and (plain.cover_id, plain.place) == (7, None)
