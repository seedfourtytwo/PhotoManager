"""Send to a device: the link (token, one use, expiry, guessing limit) on the real SQLite store."""

import hashlib
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_handover import SqliteHandovers
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.handover import HandoverNotFoundError, HandoverRules, Handovers
from photo_assistant.domain.access import Role, User
from photo_assistant.domain.errors import ConflictError, ForbiddenError, InvalidError
from photo_assistant.domain.handover import (
    KEPT,
    MAX_WRONG_TOKENS_OVERALL,
    MAX_WRONG_TOKENS_PER_CLIENT,
    WRONG_TOKEN_WINDOW,
    HandoverGoneError,
    HandoverState,
    TooManyTriesError,
)
from tests.fakes import FakeClock

PHONE = "100.64.0.7"
RULES = HandoverRules(minutes=10, unencrypted_allowed=True)


def _user(repo: SqliteRepository, name: str, role: Role = Role.MEMBER) -> User:
    return repo.add_user(name, name.title(), "hash", role)


@pytest.fixture
def lea(repo: SqliteRepository) -> User:
    return _user(repo, "lea")


@pytest.fixture
def handovers(db: Database, clock: FakeClock) -> Handovers:
    return Handovers(SqliteHandovers(db), clock, RULES)


def _send(handovers: Handovers, user: User, ids: list[int] | None = None) -> tuple[int, str]:
    handover, token = handovers.create(
        user, ids or [3, 4], 2000, encrypted=True, details_removed=True
    )
    return handover.id, token


# --- the token ------------------------------------------------------------------------------


def test_a_token_is_256_random_url_safe_bits_and_only_its_hash_is_stored(
    handovers: Handovers, lea: User, conn: sqlite3.Connection
) -> None:
    _, token = _send(handovers, lea)
    _, other = _send(handovers, lea)
    assert token != other
    assert len(token) == 43 and token.replace("-", "").replace("_", "").isalnum()
    stored = [row[0] for row in conn.execute("SELECT token_hash FROM handover ORDER BY id")]
    assert stored[0] == hashlib.sha256(token.encode()).hexdigest()
    dump = "\n".join(str(tuple(row)) for row in conn.execute("SELECT * FROM handover"))
    assert token not in dump and other not in dump


def test_the_token_opens_its_hand_over_with_what_was_asked(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    handover, token = handovers.create(
        lea, [9, 3, 9], 5000, encrypted=False, details_removed=False, confirmed_unencrypted=True
    )
    found = handovers.find(token, PHONE)
    assert found == handover
    assert found.asset_ids == (9, 3) and found.byte_size == 5000
    assert found.created_by == lea.id and not found.encrypted and not found.details_removed
    assert found.expires_at == clock.now() + timedelta(minutes=10)
    assert found.max_redemptions == 1 and found.state(clock.now()) is HandoverState.WAITING


def test_the_lifetime_is_the_admins_setting(db: Database, clock: FakeClock, lea: User) -> None:
    quick = Handovers(SqliteHandovers(db), clock, HandoverRules(2, True))
    handover, _ = quick.create(lea, [1], 10, encrypted=True, details_removed=True)
    assert handover.expires_at - handover.created_at == timedelta(minutes=2)
    with pytest.raises(InvalidError):
        Handovers(SqliteHandovers(db), clock, HandoverRules(0, True))


# --- refusals when making one ---------------------------------------------------------------


def test_nothing_is_stored_for_a_refused_link(
    handovers: Handovers, lea: User, conn: sqlite3.Connection
) -> None:
    with pytest.raises(InvalidError):
        handovers.create(lea, [], 0, encrypted=True, details_removed=True)
    with pytest.raises(ConflictError):  # unencrypted and not confirmed
        handovers.create(lea, [1], 10, encrypted=False, details_removed=True)
    assert conn.execute("SELECT COUNT(*) FROM handover").fetchone()[0] == 0


def test_unencrypted_links_can_be_switched_off(db: Database, clock: FakeClock, lea: User) -> None:
    strict = Handovers(SqliteHandovers(db), clock, HandoverRules(10, False))
    with pytest.raises(ForbiddenError):
        strict.create(
            lea, [1], 10, encrypted=False, details_removed=True, confirmed_unencrypted=True
        )
    strict.create(lea, [1], 10, encrypted=True, details_removed=True)


# --- collecting -----------------------------------------------------------------------------


def test_collecting_uses_the_link_up_and_writes_down_who_took_it(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    handover_id, token = _send(handovers, lea)
    clock.advance(timedelta(minutes=3))
    handovers.collect(handovers.find(token, PHONE), PHONE, "Mozilla/5.0 (iPhone)\n")
    taken = handovers.get_for(lea, handover_id)
    assert taken.state(clock.now()) is HandoverState.REDEEMED
    assert taken.redeemed_at == clock.now() and taken.redeemed_from == PHONE
    assert taken.redeemed_agent == "Mozilla/5.0 (iPhone)"
    with pytest.raises(HandoverGoneError):
        handovers.find(token, PHONE)


def test_wrong_used_expired_and_cancelled_tokens_get_the_same_answer(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    _, used = _send(handovers, lea)
    handovers.collect(handovers.find(used, PHONE), PHONE, None)
    cancelled_id, cancelled = _send(handovers, lea)
    handovers.cancel(lea, cancelled_id)
    _, expired = _send(handovers, lea)
    clock.advance(timedelta(minutes=10))  # exactly at the boundary
    answers = set()
    for token in ("never-issued", used, cancelled, expired):
        with pytest.raises(HandoverGoneError) as refused:
            handovers.find(token, PHONE)
        answers.add((refused.value.status, str(refused.value)))
    assert len(answers) == 1


def test_a_link_that_ran_out_between_look_and_tap_is_not_collected(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    _, token = _send(handovers, lea)
    seen = handovers.find(token, PHONE)
    clock.advance(timedelta(minutes=10))
    with pytest.raises(HandoverGoneError):
        handovers.collect(seen, PHONE, None)


def test_two_devices_at_the_same_moment_exactly_one_collects(tmp_path: Path) -> None:
    """Both have looked the link up (it waits for both); the one statement that collects
    decides. On a database file, with a reader per thread, as the server runs."""
    db = Database.open(tmp_path / "library.db")
    clock = FakeClock()
    handovers = Handovers(SqliteHandovers(db), clock, RULES)
    lea = _user(SqliteRepository(db), "lea")
    racers = 8
    for _ in range(20):
        handover_id, token = _send(handovers, lea)
        seen = handovers.find(token, PHONE)
        start = threading.Barrier(racers, timeout=5)
        outcomes: list[str] = []

        def tap(n: int, seen=seen, start=start, outcomes=outcomes) -> None:  # type: ignore[no-untyped-def]
            start.wait()
            try:
                handovers.collect(seen, f"100.64.0.{n}", None)
            except HandoverGoneError:
                outcomes.append("gone")
            else:
                outcomes.append("won")

        threads = [threading.Thread(target=tap, args=(n,)) for n in range(racers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(outcomes) == ["gone"] * (racers - 1) + ["won"]
        assert handovers.get_for(lea, handover_id).redemptions == 1
    db.close()


# --- cancelling, and whose it is ------------------------------------------------------------


def test_cancelling_stops_a_waiting_link_and_only_that(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    handover_id, token = _send(handovers, lea)
    handovers.cancel(lea, handover_id)
    assert handovers.get_for(lea, handover_id).state(clock.now()) is HandoverState.CANCELLED
    with pytest.raises(HandoverGoneError):
        handovers.find(token, PHONE)
    with pytest.raises(ConflictError, match="already cancelled"):
        handovers.cancel(lea, handover_id)
    taken_id, taken = _send(handovers, lea)
    handovers.collect(handovers.find(taken, PHONE), PHONE, None)
    with pytest.raises(ConflictError, match="already downloaded"):
        handovers.cancel(lea, taken_id)


def test_a_member_manages_their_own_an_admin_everyones(
    handovers: Handovers, lea: User, repo: SqliteRepository
) -> None:
    tom, admin = _user(repo, "tom"), _user(repo, "c", Role.ADMIN)
    mine, _ = _send(handovers, lea)
    toms, _ = _send(handovers, tom)
    assert [h.id for h in handovers.list_for(lea)] == [mine]
    assert [h.id for h in handovers.list_for(admin)] == [toms, mine]  # newest first
    with pytest.raises(HandoverNotFoundError):
        handovers.get_for(lea, toms)
    with pytest.raises(HandoverNotFoundError):
        handovers.cancel(lea, toms)
    with pytest.raises(HandoverNotFoundError):
        handovers.get_for(admin, 999)
    handovers.cancel(admin, toms)


def test_a_burnt_link_is_cancelled(handovers: Handovers, lea: User, clock: FakeClock) -> None:
    handover_id, token = _send(handovers, lea)
    handovers.burn(handovers.find(token, PHONE))
    assert handovers.get_for(lea, handover_id).state(clock.now()) is HandoverState.CANCELLED


# --- guessing -------------------------------------------------------------------------------


def test_a_client_that_keeps_trying_wrong_tokens_has_to_wait(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    _, token = _send(handovers, lea)
    for _ in range(MAX_WRONG_TOKENS_PER_CLIENT):
        with pytest.raises(HandoverGoneError):
            handovers.find("guess", PHONE)
    with pytest.raises(TooManyTriesError):
        handovers.find(token, PHONE)  # the right one too: no way to tell them apart by trying
    assert handovers.find(token, "100.64.0.8").collectable(clock.now()), "other clients go on"
    clock.advance(WRONG_TOKEN_WINDOW)
    _, fresh = _send(handovers, lea)
    assert handovers.find(fresh, PHONE), "the wait is over with the window"


def test_wrong_tokens_from_many_clients_stop_everyone_for_the_window(
    handovers: Handovers, lea: User, clock: FakeClock
) -> None:
    _, token = _send(handovers, lea)
    for n in range(MAX_WRONG_TOKENS_OVERALL):
        with pytest.raises(HandoverGoneError):
            handovers.find("guess", f"client-{n}")
    with pytest.raises(TooManyTriesError):
        handovers.find(token, "someone-new")
    with pytest.raises(TooManyTriesError):  # a refused try is not counted again
        handovers.find("guess", "client-0")
    clock.advance(WRONG_TOKEN_WINDOW)
    with pytest.raises(HandoverGoneError):  # the link itself ran out meanwhile
        handovers.find(token, "someone-new")


# --- housekeeping ---------------------------------------------------------------------------


def test_the_trail_is_kept_ninety_days(handovers: Handovers, lea: User, clock: FakeClock) -> None:
    old, _ = _send(handovers, lea)
    clock.advance(KEPT)
    kept, _ = _send(handovers, lea)
    assert handovers.prune() == 0  # exactly 90 days old: still there
    clock.advance(timedelta(seconds=1))
    assert handovers.prune() == 1
    assert [h.id for h in handovers.list_for(lea)] == [kept] and old != kept


def test_hand_overs_go_with_their_account(
    handovers: Handovers, lea: User, conn: sqlite3.Connection
) -> None:
    _send(handovers, lea)
    conn.execute("DELETE FROM user WHERE id = ?", (lea.id,))
    assert conn.execute("SELECT COUNT(*) FROM handover").fetchone()[0] == 0
