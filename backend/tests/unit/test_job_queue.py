"""The job queue's timing rules: how long a failed job waits, and when a claim is stale."""

from datetime import timedelta

import pytest

from photo_assistant.domain.job_queue import (
    CLAIM_STALE_AFTER,
    HEARTBEAT_INTERVAL,
    RETRY_DELAYS,
    STALE_SWEEP_INTERVAL,
    retry_delay,
)


@pytest.mark.parametrize(
    ("failed_attempts", "minutes"),
    [(1, 1), (2, 5), (3, 25)],
)
def test_each_retry_waits_longer_than_the_one_before(failed_attempts: int, minutes: int) -> None:
    assert retry_delay(failed_attempts) == timedelta(minutes=minutes)


def test_later_attempts_keep_the_longest_delay() -> None:
    assert retry_delay(4) == retry_delay(99) == RETRY_DELAYS[-1]


def test_an_attempt_number_below_one_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="attempt"):
        retry_delay(0)


def test_a_claim_survives_many_missed_heartbeats_before_it_counts_as_stale() -> None:
    """A busy database or a slow disk may delay a heartbeat; that must not requeue a job."""
    assert CLAIM_STALE_AFTER >= 5 * HEARTBEAT_INTERVAL
    assert STALE_SWEEP_INTERVAL > HEARTBEAT_INTERVAL, "see StaleJobSweep: after a suspend"
