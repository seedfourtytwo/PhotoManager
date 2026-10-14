"""Rediscover on Home (issue 54): a dozen photos from across the years, a new dozen each day."""

from datetime import date, datetime, timedelta

from photo_assistant.domain.memories import Moment, by_time
from photo_assistant.domain.rediscover import RECENT, SHOWN, rediscover

TODAY = date(2026, 10, 14)


def month_of_photos(
    year: int, month: int, n: int = 3, *, first_id: int, loved: int | None = None
) -> list[Moment]:
    """``n`` photos on the first days of a month; ``loved``: the index of a favourite."""
    start = datetime(year, month, 1, 10)
    return [
        Moment(first_id + i, start + timedelta(days=i), None, favourite=i == loved)
        for i in range(n)
    ]


def library(years: range, months: tuple[int, ...] = (3, 8)) -> list[Moment]:
    photos: list[Moment] = []
    for year in years:
        for month in months:
            photos += month_of_photos(year, month, first_id=year * 1000 + month * 10)
    return by_time(photos)


def ids(found: list[Moment]) -> list[int]:
    return [m.asset_id for m in found]


def test_an_empty_library_has_nothing_to_rediscover() -> None:
    assert rediscover([], TODAY) == []


def test_a_single_photo_is_rediscovered_even_when_it_is_new() -> None:
    only = [Moment(1, datetime(2026, 10, 13, 9), None)]
    assert rediscover(only, TODAY) == only


def test_a_dozen_from_a_dozen_years_before_a_second_from_any_year() -> None:
    found = rediscover(library(range(2011, 2026)), TODAY)
    assert len(found) == SHOWN
    assert len({m.taken_at.year for m in found}) == SHOWN, "one photo per year"


def test_few_years_give_several_photos_each_from_different_months() -> None:
    found = rediscover(library(range(2023, 2026), months=(1, 3, 5, 7, 9, 11)), TODAY)
    assert len(found) == SHOWN
    per_year = [sum(m.taken_at.year == y for m in found) for y in (2023, 2024, 2025)]
    assert per_year == [4, 4, 4], "the years take turns"
    assert len({(m.taken_at.year, m.taken_at.month) for m in found}) == SHOWN


def test_all_of_a_small_library_shows_when_it_has_fewer_months_than_a_dozen() -> None:
    photos = library(range(2015, 2018), months=(6,))  # three months, three photos each
    assert len(rediscover(photos, TODAY)) == 3, "one per month"


def test_a_favourite_wins_its_month_and_comes_first() -> None:
    photos = library(range(2023, 2026), months=(1, 4, 7, 10))  # a dozen months: all shown
    loved = month_of_photos(2024, 4, first_id=90_000, loved=2)  # more of April 2024
    found = rediscover(by_time(photos + loved), TODAY)
    assert found[0].asset_id == 90_002, "the favourite leads"
    assert all(not m.favourite for m in found[1:])


def test_after_the_first_the_photos_run_oldest_to_newest() -> None:
    found = rediscover(library(range(2011, 2026)), TODAY)
    rest = [m.taken_at for m in found[1:]]
    assert rest == sorted(rest)


def test_it_stays_the_same_all_day_and_turns_the_next() -> None:
    photos = library(range(2005, 2026))  # more years than a dozen
    today = rediscover(photos, TODAY)
    assert rediscover(photos, TODAY) == today
    tomorrow = rediscover(photos, TODAY + timedelta(days=1))
    assert set(ids(tomorrow)) != set(ids(today))


def test_the_last_30_days_are_left_out_while_older_photos_exist() -> None:
    cutoff = datetime.combine(TODAY - RECENT, datetime.min.time())
    older = Moment(1, cutoff - timedelta(minutes=1), None)
    recent = [Moment(2, cutoff, None), Moment(3, datetime(2026, 10, 14, 8), None)]
    assert rediscover([older, *recent], TODAY) == [older]
    assert sorted(ids(rediscover(recent, TODAY))) == [2, 3], "only new ones: they are what there is"


def test_on_the_leap_day_30_days_reach_back_to_30_january() -> None:
    leap_day = date(2028, 2, 29)
    older = Moment(1, datetime(2028, 1, 29, 23, 59), None)
    recent = Moment(2, datetime(2028, 1, 30, 0, 0), None)
    assert rediscover([older, recent], leap_day) == [older]
    photos = library(range(2005, 2026))
    assert rediscover(photos, leap_day) != rediscover(photos, date(2028, 3, 1))
