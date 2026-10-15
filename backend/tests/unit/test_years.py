"""Years on Home (issue 54): each year with ten dated photos, as a memory of that whole year."""

from datetime import date, datetime, timedelta

from photo_assistant.domain.memories import MIN_PHOTOS, Memory, Moment, by_time
from photo_assistant.domain.years import years

TODAY = date(2026, 10, 14)


def in_year(year: int, n: int, *, first_id: int, loved: int | None = None) -> list[Moment]:
    """``n`` photos, one every three days from 1 January; ``loved``: the index of a favourite."""
    start = datetime(year, 1, 1, 10)
    return [
        Moment(first_id + i, start + i * timedelta(days=3), None, favourite=i == loved)
        for i in range(n)
    ]


def test_an_empty_library_has_no_years() -> None:
    assert years([], TODAY) == []


def test_a_single_photo_makes_no_year() -> None:
    assert years([Moment(1, datetime(2016, 3, 12, 9), "Lisbon")], TODAY) == []


def test_a_year_needs_ten_photos() -> None:
    assert years(in_year(2016, MIN_PHOTOS - 1, first_id=1), TODAY) == []
    (found,) = years(in_year(2016, MIN_PHOTOS, first_id=1), TODAY)
    assert found == Memory(
        key="2016-01-01_2016-12-31",
        title="2016",
        first_day=date(2016, 1, 1),
        last_day=date(2016, 12, 31),
        count=MIN_PHOTOS,
        cover_id=found.cover_id,
    )


def test_newest_year_first_without_any_place() -> None:
    photos = by_time(in_year(2015, 12, first_id=100) + in_year(2019, 30, first_id=200))
    assert [(y.title, y.count) for y in years(photos, TODAY)] == [("2019", 30), ("2015", 12)]


def test_the_cover_is_a_favourite_of_that_year() -> None:
    (found,) = years(in_year(2016, 20, first_id=1, loved=7), TODAY)
    assert found.cover_id == 8
    assert years(in_year(2016, 20, first_id=1, loved=7), TODAY + timedelta(days=1)) == [found]


def test_without_a_favourite_the_cover_changes_each_day_and_stays_all_day() -> None:
    photos = in_year(2016, 20, first_id=1)
    (today,) = years(photos, TODAY)
    assert years(photos, TODAY) == [today]
    (tomorrow,) = years(photos, TODAY + timedelta(days=1))
    assert tomorrow.cover_id != today.cover_id
    assert tomorrow.key == today.key


def test_a_leap_year_counts_29_february_and_ends_on_31_december() -> None:
    photos = [*in_year(2024, 9, first_id=1), Moment(99, datetime(2024, 2, 29, 12), None)]
    (leap,) = years(by_time(photos), date(2028, 2, 29))
    assert (leap.count, leap.last_day) == (10, date(2024, 12, 31))
