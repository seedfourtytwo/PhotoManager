"""Send to a device: the pure rules of a hand-over (spec 2026-10-13).

A hand-over is a fixed list of photos, good for ten minutes and one collection. Its state is
worked out from what is recorded, never stored.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from photo_assistant.domain.errors import ConflictError, ForbiddenError, InvalidError
from photo_assistant.domain.handover import (
    DEFAULT_MINUTES,
    MAX_BYTES,
    MAX_MINUTES,
    MAX_PHOTOS,
    MAX_WRONG_TOKENS_OVERALL,
    MAX_WRONG_TOKENS_PER_CLIENT,
    MIN_MINUTES,
    NEUTRAL_NAME,
    Handover,
    HandoverState,
    check_cancellable,
    check_size,
    check_transport,
    clean_agent,
    export_options,
    file_names,
    lifetime,
    may_travel,
    too_many_wrong_tokens,
    unique_ids,
)
from tests.factories import NOW

EXPIRES = NOW + timedelta(minutes=10)


def handover(**changes: object) -> Handover:
    base = Handover(
        id=1,
        created_by=7,
        created_at=NOW,
        expires_at=EXPIRES,
        asset_ids=(3, 4),
        byte_size=2000,
        encrypted=True,
        details_removed=True,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


# --- state ----------------------------------------------------------------------------------


def test_a_new_hand_over_waits() -> None:
    assert handover().state(NOW) is HandoverState.WAITING


@pytest.mark.parametrize(
    ("after", "state"),
    [
        (timedelta(minutes=10) - timedelta(microseconds=1), HandoverState.WAITING),
        (timedelta(minutes=10), HandoverState.EXPIRED),  # exactly at the boundary: over
        (timedelta(minutes=10, seconds=1), HandoverState.EXPIRED),
    ],
)
def test_it_runs_out_exactly_at_its_expiry_time(after: timedelta, state: HandoverState) -> None:
    assert handover().state(NOW + after) is state


def test_collected_once_it_is_redeemed_and_stays_so_after_its_time() -> None:
    taken = handover(redemptions=1, redeemed_at=NOW)
    assert taken.state(NOW) is HandoverState.REDEEMED
    assert taken.state(EXPIRES + timedelta(hours=1)) is HandoverState.REDEEMED


def test_it_cannot_be_collected_twice() -> None:
    assert handover().collectable(NOW)
    assert not handover(redemptions=1, redeemed_at=NOW).collectable(NOW)


def test_one_that_allows_two_collections_waits_after_the_first() -> None:
    twice = handover(max_redemptions=2, redemptions=1, redeemed_at=NOW)
    assert twice.state(NOW) is HandoverState.WAITING and twice.collectable(NOW)
    assert replace(twice, redemptions=2).state(NOW) is HandoverState.REDEEMED
    # its time over with one collection made: what happened is that it was collected
    assert twice.state(EXPIRES) is HandoverState.REDEEMED and not twice.collectable(EXPIRES)


def test_cancelled_wins_over_everything_and_cannot_be_collected() -> None:
    cancelled = handover(cancelled_at=NOW)
    assert cancelled.state(NOW) is HandoverState.CANCELLED
    assert cancelled.state(EXPIRES) is HandoverState.CANCELLED
    assert not cancelled.collectable(NOW)


def test_an_expired_one_cannot_be_collected() -> None:
    assert not handover().collectable(EXPIRES)


# --- cancelling -----------------------------------------------------------------------------


def test_only_a_waiting_hand_over_can_be_cancelled() -> None:
    check_cancellable(handover(), NOW)
    for done in (
        handover(redemptions=1, redeemed_at=NOW),
        handover(cancelled_at=NOW),
    ):
        with pytest.raises(ConflictError):
            check_cancellable(done, NOW)
    with pytest.raises(ConflictError, match="run out"):
        check_cancellable(handover(), EXPIRES)


# --- lifetime -------------------------------------------------------------------------------


def test_the_default_lifetime_is_ten_minutes() -> None:
    assert DEFAULT_MINUTES == 10
    assert lifetime(DEFAULT_MINUTES) == timedelta(minutes=10)


@pytest.mark.parametrize("minutes", [MIN_MINUTES, MAX_MINUTES])
def test_the_lifetime_may_be_set_within_a_tight_range(minutes: int) -> None:
    assert (MIN_MINUTES, MAX_MINUTES) == (1, 60)
    assert lifetime(minutes) == timedelta(minutes=minutes)


@pytest.mark.parametrize("minutes", [0, -5, MAX_MINUTES + 1, 24 * 60])
def test_a_lifetime_outside_the_range_is_refused(minutes: int) -> None:
    with pytest.raises(InvalidError, match="1 to 60 minutes"):
        lifetime(minutes)


# --- what may be sent -----------------------------------------------------------------------


def test_ids_are_sent_once_each_in_the_order_given() -> None:
    assert unique_ids([5, 3, 5, 9, 3]) == (5, 3, 9)


def test_nothing_to_send_is_refused() -> None:
    with pytest.raises(InvalidError, match="at least one photo"):
        check_size(0, 0)


def test_the_most_photos_and_bytes_pass_and_one_more_does_not() -> None:
    check_size(MAX_PHOTOS, MAX_BYTES)
    with pytest.raises(InvalidError, match=f"at most {MAX_PHOTOS} photos"):
        check_size(MAX_PHOTOS + 1, 1)
    with pytest.raises(InvalidError, match="too big"):
        check_size(1, MAX_BYTES + 1)


# --- the copy that is sent ------------------------------------------------------------------


def test_photos_go_as_full_size_jpegs_any_phone_opens() -> None:
    options = export_options(details_removed=False)
    assert (options.format, options.max_edge) == ("jpeg", None)
    assert not options.strip_all_metadata and not options.strip_location


def test_removing_details_strips_all_metadata_from_the_copy() -> None:
    assert export_options(details_removed=True).strip_all_metadata


def test_file_names_are_kept_unless_details_are_removed() -> None:
    names = ["IMG_20180312_091500.jpg", "Léa's iPhone 004.heic"]
    assert file_names(names, details_removed=False) == names
    # a name can carry a date or a device: none of it leaves
    assert file_names(names, details_removed=True) == [NEUTRAL_NAME, NEUTRAL_NAME]


# --- encrypted or not -----------------------------------------------------------------------


def test_an_encrypted_link_needs_no_confirmation() -> None:
    check_transport(encrypted=True, unencrypted_allowed=False, confirmed=False)


def test_an_unencrypted_link_needs_the_senders_yes_each_time() -> None:
    with pytest.raises(ConflictError, match="not encrypted"):
        check_transport(encrypted=False, unencrypted_allowed=True, confirmed=False)
    check_transport(encrypted=False, unencrypted_allowed=True, confirmed=True)


def test_an_admin_can_forbid_unencrypted_sending_whatever_the_sender_says() -> None:
    with pytest.raises(ForbiddenError, match="https"):
        check_transport(encrypted=False, unencrypted_allowed=False, confirmed=True)


@pytest.mark.parametrize(
    ("promised", "arrived", "ok"),
    [(True, True, True), (True, False, False), (False, False, True), (False, True, True)],
)
def test_a_link_promised_as_encrypted_is_never_collected_in_the_clear(
    promised: bool, arrived: bool, ok: bool
) -> None:
    assert may_travel(handover(encrypted=promised), arrived_encrypted=arrived) is ok


# --- guessing -------------------------------------------------------------------------------


def test_wrong_tokens_are_limited_per_client_and_overall() -> None:
    assert not too_many_wrong_tokens(MAX_WRONG_TOKENS_PER_CLIENT - 1, 0)
    assert too_many_wrong_tokens(MAX_WRONG_TOKENS_PER_CLIENT, 0)
    assert not too_many_wrong_tokens(0, MAX_WRONG_TOKENS_OVERALL - 1)
    assert too_many_wrong_tokens(0, MAX_WRONG_TOKENS_OVERALL)


# --- the trail ------------------------------------------------------------------------------


def test_what_a_browser_calls_itself_is_kept_short_and_printable() -> None:
    assert clean_agent("Mozilla/5.0 (iPhone)\x1b[31m\n") == "Mozilla/5.0 (iPhone)[31m"
    assert len(clean_agent("x" * 5000) or "") == 200
    assert clean_agent("  ") is None and clean_agent(None) is None
