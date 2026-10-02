from datetime import datetime, timedelta, timezone

import pytest

from photo_assistant.domain.date_fix import DateFixError, new_capture_times

NOW = datetime(2026, 10, 2, 12, 0)

A = datetime(2020, 10, 26, 12, 0)
B = datetime(2021, 1, 1, 0, 0)


def test_set_gives_every_photo_the_same_time_without_zone() -> None:
    target = datetime(2019, 7, 4, 18, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
    assert new_capture_times([(1, A), (2, B)], target, None, NOW) == [
        (1, datetime(2019, 7, 4, 18, 30, 5)),
        (2, datetime(2019, 7, 4, 18, 30, 5)),
    ]


def test_shift_moves_each_photo_by_the_same_amount() -> None:
    assert new_capture_times([(1, A), (2, B)], None, -90, NOW) == [
        (1, datetime(2020, 10, 26, 10, 30)),
        (2, datetime(2020, 12, 31, 22, 30)),
    ]


@pytest.mark.parametrize(
    ("set_to", "shift"),
    [
        (None, None),
        (A, 5),
        (datetime(1700, 1, 1), None),
        (None, -60 * 24 * 365 * 300),
        (None, 10**12),
    ],
)
def test_impossible_changes_are_refused(set_to: datetime | None, shift: int | None) -> None:
    with pytest.raises(DateFixError):
        new_capture_times([(1, A)], set_to, shift, NOW)


def test_nothing_may_end_up_more_than_a_day_in_the_future() -> None:
    """QA A11: dates could be set or shifted into the year 9999."""
    new_capture_times([(1, A)], NOW.replace(hour=23), None, NOW)  # later today: fine
    with pytest.raises(DateFixError, match="future"):
        new_capture_times([(1, A)], datetime(2026, 10, 4), None, NOW)
    with pytest.raises(DateFixError, match="future"):
        new_capture_times([(1, NOW)], None, 60 * 25, NOW)
