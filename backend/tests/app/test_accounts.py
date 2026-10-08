"""Accounts use case: setup, login, sessions, rate limit, user admin (FEATURES 8.1, 11.10)."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.accounts import (
    AccountError,
    AccountLockedError,
    Accounts,
    AlreadySetUpError,
    InvalidCredentialsError,
    LastAdminError,
    NotFoundError,
    TooManyAttemptsError,
    UserPatch,
)
from photo_assistant.domain.access import FAILED_LOGIN_WINDOW, Role
from tests.factories import NOW

GOOD = "1234"
IP = "10.0.0.1"


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


class MovableClock:
    def __init__(self) -> None:
        self.at = NOW

    def now(self) -> datetime:
        return self.at


@pytest.fixture
def clock() -> MovableClock:
    return MovableClock()


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


@pytest.fixture
def accounts(repo: SqliteRepository, clock: MovableClock) -> Accounts:
    return Accounts(repo, FakeHasher(), clock)


def test_first_run_creates_the_admin_and_a_session(accounts: Accounts) -> None:
    assert accounts.needs_admin()
    user, token = accounts.setup("c", "C", GOOD)
    assert user.role is Role.ADMIN and not accounts.needs_admin()
    assert accounts.authenticate(token) == user
    with pytest.raises(AlreadySetUpError):
        accounts.setup("other", "Other", GOOD)


def test_setup_gives_ownerless_sources_to_the_first_admin(
    accounts: Accounts, repo: SqliteRepository
) -> None:
    source = repo.add_source("Old", "/old")
    user, _ = accounts.setup("c", "C", GOOD)
    claimed = repo.get_source(source.id)
    assert claimed is not None and claimed.owner_id == user.id


def test_pins_are_hashed_and_checked(accounts: Accounts, repo: SqliteRepository) -> None:
    accounts.setup("c", "C", GOOD)
    stored = repo.find_user_by_username("C")
    assert stored is not None and stored[1] == f"hashed:{GOOD}", "usernames ignore case"
    user, token = accounts.login("c", GOOD, "10.0.0.1")
    assert accounts.authenticate(token) == user
    with pytest.raises(InvalidCredentialsError):
        accounts.login("c", "0000", "10.0.0.1")
    with pytest.raises(InvalidCredentialsError):
        accounts.login("nobody", GOOD, "10.0.0.1")


def test_ten_wrong_pins_in_fifteen_minutes_block_the_account_from_every_address(
    accounts: Accounts, clock: MovableClock
) -> None:
    accounts.setup("c", "C", GOOD)
    for n in range(10):
        with pytest.raises(InvalidCredentialsError):
            accounts.login("c", "0000", f"10.0.0.{n}")  # ten addresses, one account
    with pytest.raises(TooManyAttemptsError, match=r"wait 15 minutes .* ask an admin"):
        accounts.login("c", GOOD, "10.0.0.99")  # an address that never guessed
    clock.at += timedelta(minutes=9, seconds=30)
    with pytest.raises(TooManyAttemptsError, match="wait 6 minutes"):
        accounts.login("c", GOOD, "10.0.0.1")
    clock.at += timedelta(minutes=5, seconds=31)
    accounts.login("C", GOOD, "10.0.0.1")  # the window is over


def test_an_admin_unlock_lifts_the_wait_for_that_account_only(accounts: Accounts) -> None:
    admin, _ = accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    for name in ("lea", "LEA", "c"):
        for n in range(5 if name != "c" else 10):
            with pytest.raises(InvalidCredentialsError):
                accounts.login(name, "0000", f"10.0.0.{n}")
    with pytest.raises(TooManyAttemptsError):
        accounts.login("Lea", GOOD, "10.0.0.8")  # names ignore case: one account, one count
    accounts.unlock(lea.id)
    accounts.login("lea", GOOD, "10.0.0.9")
    with pytest.raises(TooManyAttemptsError):
        accounts.login("c", GOOD, "10.0.0.9")  # someone else stays blocked
    with pytest.raises(NotFoundError):
        accounts.unlock(999)
    assert admin.role is Role.ADMIN


def test_sessions_expire_after_thirty_idle_days_and_use_keeps_them_alive(
    accounts: Accounts, clock: MovableClock
) -> None:
    _, token = accounts.setup("c", "C", GOOD)
    clock.at += timedelta(days=20)
    assert accounts.authenticate(token) is not None
    clock.at += timedelta(days=20)
    assert accounts.authenticate(token) is not None, "used 20 days ago: still alive"
    clock.at += timedelta(days=31)
    assert accounts.authenticate(token) is None
    assert accounts.authenticate(token) is None, "expired sessions are deleted"
    assert accounts.authenticate("made-up") is None


def test_logout_ends_the_session(accounts: Accounts) -> None:
    _, token = accounts.setup("c", "C", GOOD)
    accounts.logout(token)
    assert accounts.authenticate(token) is None


def test_change_pin_checks_the_current_one(accounts: Accounts) -> None:
    user, token = accounts.setup("c", "C", GOOD)
    _, other = accounts.login("c", GOOD, "2.2.2.2")
    with pytest.raises(InvalidCredentialsError):
        accounts.change_pin(user, "0000", "5678", token, IP)
    with pytest.raises(AccountError, match="4 digits"):
        accounts.change_pin(user, GOOD, "12345", token, IP)
    assert accounts.authenticate(other) is not None, "failed attempts change nothing"
    accounts.change_pin(user, GOOD, "5678", token, IP)
    accounts.login("c", "5678", "1.1.1.1")
    assert accounts.authenticate(token) is not None
    assert accounts.authenticate(other) is None


def test_admin_creates_and_updates_users(accounts: Accounts) -> None:
    admin, _ = accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    assert [u.username for u in accounts.list_users()] == ["c", "lea"]
    with pytest.raises(AccountError, match="taken"):
        accounts.create_user("LEA", "Other", GOOD, Role.GUEST)
    with pytest.raises(AccountError, match="user names"):
        accounts.create_user("bad name", "x", GOOD, Role.GUEST)
    with pytest.raises(AccountError, match="4 digits"):
        accounts.create_user("tom", "Tom", "12345", Role.GUEST)
    updated = accounts.update_user(lea.id, UserPatch(display_name="Lea M", role=Role.GUEST))
    assert updated.display_name == "Lea M" and updated.role is Role.GUEST
    accounts.update_user(lea.id, UserPatch(pin="9012"))
    accounts.login("lea", "9012", "1.1.1.1")
    with pytest.raises(NotFoundError):
        accounts.update_user(999, UserPatch(disabled=True))
    assert admin.id != lea.id


def test_login_names_are_the_active_accounts(accounts: Accounts) -> None:
    assert accounts.login_names() == []
    accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    assert accounts.login_names() == [("c", "C"), ("lea", "Léa")]
    accounts.update_user(lea.id, UserPatch(disabled=True))
    assert accounts.login_names() == [("c", "C")]


def test_disabling_a_user_ends_their_sessions_and_blocks_login(accounts: Accounts) -> None:
    accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    _, token = accounts.login("lea", GOOD, "1.1.1.1")
    accounts.update_user(lea.id, UserPatch(disabled=True))
    assert accounts.authenticate(token) is None
    with pytest.raises(InvalidCredentialsError):
        accounts.login("lea", GOOD, "1.1.1.1")


def test_the_last_admin_cannot_be_demoted_or_disabled(accounts: Accounts) -> None:
    admin, _ = accounts.setup("c", "C", GOOD)
    with pytest.raises(LastAdminError):
        accounts.update_user(admin.id, UserPatch(role=Role.MEMBER))
    with pytest.raises(LastAdminError):
        accounts.update_user(admin.id, UserPatch(disabled=True))
    other = accounts.create_user("lea", "Léa", GOOD, Role.ADMIN)
    accounts.update_user(admin.id, UserPatch(role=Role.MEMBER))
    with pytest.raises(LastAdminError):
        accounts.update_user(other.id, UserPatch(disabled=True))


def test_create_user_from_the_command_line_needs_no_session(accounts: Accounts) -> None:
    user = accounts.create_user("c", "c", GOOD, Role.ADMIN)
    assert not accounts.needs_admin()
    assert user.role is Role.ADMIN


# --- QA A8: check-then-write races -------------------------------------------------------------


class RacingStore:
    """The real store, except that every reader of a count waits until all racers read it."""

    def __init__(self, repo: SqliteRepository, racers: int) -> None:
        import threading

        self._repo = repo
        self._barrier = threading.Barrier(racers, timeout=5)

    def __getattr__(self, name: str) -> object:
        return getattr(self._repo, name)

    def count_users(self) -> int:
        n = self._repo.count_users()
        self._barrier.wait()
        return n

    def count_active_admins(self) -> int:
        n = self._repo.count_active_admins()
        self._barrier.wait()
        return n


def _race(*calls: object) -> list[BaseException | None]:
    import threading

    outcomes: list[BaseException | None] = [None] * len(calls)

    def run(i: int) -> None:
        try:
            calls[i]()  # type: ignore[operator]
        except BaseException as exc:  # recorded and asserted on below
            outcomes[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return outcomes


def test_concurrent_first_run_setups_create_exactly_one_admin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = SqliteRepository(open_database(tmp_path / "library.db"))
    accounts = Accounts(RacingStore(repo, 3), FakeHasher(), MovableClock())  # type: ignore[arg-type]
    outcomes = _race(*(lambda n=n: accounts.setup(f"admin{n}", "A", GOOD) for n in range(3)))
    assert repo.count_users() == 1
    assert sum(o is None for o in outcomes) == 1
    assert all(isinstance(o, AlreadySetUpError) for o in outcomes if o is not None)


def test_two_admins_demoting_each_other_at_once_leave_one_admin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = SqliteRepository(open_database(tmp_path / "library.db"))
    plain = Accounts(repo, FakeHasher(), MovableClock())
    a, _ = plain.setup("a", "A", GOOD)
    b = plain.create_user("b", "B", GOOD, Role.ADMIN)
    racing = Accounts(RacingStore(repo, 2), FakeHasher(), MovableClock())  # type: ignore[arg-type]
    outcomes = _race(
        lambda: racing.update_user(a.id, UserPatch(role=Role.MEMBER)),
        lambda: racing.update_user(b.id, UserPatch(disabled=True)),
    )
    assert repo.count_active_admins() == 1
    assert [type(o) for o in outcomes].count(LastAdminError) == 1


# --- PIN guessing: change-PIN throttle, parallel guesses, unknown names ------------------------


def test_wrong_current_pins_count_as_failed_logins_and_block_like_them(
    accounts: Accounts, clock: MovableClock
) -> None:
    user, token = accounts.setup("c", "C", GOOD)
    for _ in range(10):
        with pytest.raises(InvalidCredentialsError):
            accounts.change_pin(user, "0000", "5678", token, IP)
    with pytest.raises(TooManyAttemptsError):
        accounts.change_pin(user, GOOD, "5678", token, IP)
    with pytest.raises(TooManyAttemptsError):
        accounts.login("c", GOOD, IP)  # one limiter: the same count as the login screen
    clock.at += timedelta(minutes=15, seconds=1)
    accounts.change_pin(user, GOOD, "5678", token, IP)
    accounts.login("c", "5678", IP)


def test_a_right_current_pin_clears_the_earlier_wrong_ones(accounts: Accounts) -> None:
    user, token = accounts.setup("c", "C", GOOD)
    for _ in range(9):
        with pytest.raises(InvalidCredentialsError):
            accounts.change_pin(user, "0000", "5678", token, IP)
    accounts.change_pin(user, GOOD, "5678", token, IP)
    for _ in range(9):
        with pytest.raises(InvalidCredentialsError):
            accounts.change_pin(user, "0000", GOOD, token, IP)
    accounts.change_pin(user, "5678", GOOD, token, IP)


class SlowCountingHasher(FakeHasher):
    """Verifying takes a moment (as argon2 does), and reports how many ran, and at once."""

    def __init__(self) -> None:
        import threading

        self._guard = threading.Lock()
        self.verified = 0
        self._running = 0
        self.most_at_once = 0

    def verify(self, password_hash: str, password: str) -> bool:
        import time

        with self._guard:
            self.verified += 1
            self._running += 1
            self.most_at_once = max(self.most_at_once, self._running)
        time.sleep(0.02)
        with self._guard:
            self._running -= 1
        return super().verify(password_hash, password)


def test_parallel_wrong_pins_cannot_get_more_guesses_than_the_limit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = SqliteRepository(open_database(tmp_path / "library.db"))
    hasher = SlowCountingHasher()
    accounts = Accounts(repo, hasher, MovableClock())
    accounts.setup("c", "C", GOOD)
    outcomes = _race(*(lambda n=n: accounts.login("c", f"{n:04d}", IP) for n in range(40)))
    assert hasher.verified == 10, "the limit is ten guesses, however they arrive"
    assert [type(o) for o in outcomes].count(InvalidCredentialsError) == 10
    assert [type(o) for o in outcomes].count(TooManyAttemptsError) == 30
    assert hasher.most_at_once <= 2, "argon2 takes 64 MiB a go: never many at once"


def test_an_unknown_user_name_is_refused_without_hashing_or_leaving_a_row(
    repo: SqliteRepository, clock: MovableClock
) -> None:
    hasher = SlowCountingHasher()
    accounts = Accounts(repo, hasher, clock)
    accounts.setup("c", "C", GOOD)
    for _ in range(25):
        with pytest.raises(InvalidCredentialsError):
            accounts.login("nobody", GOOD, IP)
    assert hasher.verified == 0
    assert repo._scalar("SELECT COUNT(*) FROM login_failure") == 0


# --- the hard lock: 30 wrong PINs since the last good sign-in ----------------------------------

WINDOW = FAILED_LOGIN_WINDOW + timedelta(seconds=1)


def _guess_wrong(accounts: Accounts, clock: MovableClock, username: str, times: int) -> None:
    """Wrong PINs, each from another address, waiting out the 15-minute block when it comes."""
    for n in range(times):
        try:
            accounts.login(username, "0000", f"10.1.{n // 250}.{n % 250}")
        except TooManyAttemptsError:
            clock.at += WINDOW
            with pytest.raises(InvalidCredentialsError):
                accounts.login(username, "0000", f"10.1.{n // 250}.{n % 250}")
        except InvalidCredentialsError:
            pass


def _locked(accounts: Accounts, username: str) -> bool:
    return next(u.locked for u in accounts.list_users() if u.username == username)


def test_thirty_wrong_pins_lock_the_account_until_someone_unlocks_it(
    accounts: Accounts, clock: MovableClock
) -> None:
    accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    _guess_wrong(accounts, clock, "lea", 29)
    assert not _locked(accounts, "lea")
    _guess_wrong(accounts, clock, "LEA", 1)
    assert _locked(accounts, "lea") and not _locked(accounts, "c")
    with pytest.raises(AccountLockedError, match=r"locked .* ask an admin .*just set-pin"):
        accounts.login("lea", GOOD, IP)  # even the right PIN
    clock.at += timedelta(days=400)
    with pytest.raises(AccountLockedError):
        accounts.login("lea", GOOD, IP)  # no window ends this one
    accounts.login("c", GOOD, IP)  # other accounts are untouched
    accounts.unlock(lea.id)
    assert not _locked(accounts, "lea")
    accounts.login("lea", GOOD, IP)


def test_a_locked_account_refuses_wrong_pins_without_checking_them(
    repo: SqliteRepository, clock: MovableClock
) -> None:
    hasher = SlowCountingHasher()
    accounts = Accounts(repo, hasher, clock)
    accounts.setup("c", "C", GOOD)
    _guess_wrong(accounts, clock, "c", 30)
    assert hasher.verified == 30
    for _ in range(5):
        with pytest.raises(AccountLockedError):
            accounts.login("c", "0000", IP)
    assert hasher.verified == 30, "a locked account gives no more guesses"


def test_the_lock_outlives_a_restart_and_the_daily_pruning(tmp_path, clock: MovableClock) -> None:  # type: ignore[no-untyped-def]
    repo = SqliteRepository(open_database(tmp_path / "library.db"))
    accounts = Accounts(repo, FakeHasher(), clock)
    accounts.setup("c", "C", GOOD)
    _guess_wrong(accounts, clock, "c", 20)
    repo.prune_login_failures(clock.at + timedelta(days=2))  # the failure rows are all gone
    _guess_wrong(accounts, clock, "c", 10)  # … and the running count still reached thirty
    repo.prune_login_failures(clock.at + timedelta(days=2))
    reopened = SqliteRepository(open_database(tmp_path / "library.db"))
    restarted = Accounts(reopened, FakeHasher(), clock)
    assert _locked(restarted, "c")
    with pytest.raises(AccountLockedError):
        restarted.login("c", GOOD, IP)


def test_a_good_sign_in_starts_the_count_again(accounts: Accounts, clock: MovableClock) -> None:
    accounts.setup("c", "C", GOOD)
    _guess_wrong(accounts, clock, "c", 29)
    clock.at += WINDOW
    accounts.login("c", GOOD, IP)
    _guess_wrong(accounts, clock, "c", 29)
    clock.at += WINDOW
    accounts.login("c", GOOD, IP)  # 58 wrong PINs in all, never 30 in a row


def test_a_new_pin_from_an_admin_or_the_command_line_lifts_the_lock(
    accounts: Accounts, clock: MovableClock
) -> None:
    admin, _ = accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    _guess_wrong(accounts, clock, "lea", 30)
    updated = accounts.update_user(lea.id, UserPatch(pin="9012"))  # Users screen: Reset PIN
    assert not updated.locked
    accounts.login("lea", "9012", IP)
    _guess_wrong(accounts, clock, "c", 30)  # the only admin: nobody is left to unlock them
    assert _locked(accounts, "c")
    assert not accounts.set_pin("c", "5678").locked  # just set-pin c
    accounts.login("c", "5678", IP)
    assert admin.id != lea.id


def test_changes_other_than_the_pin_leave_the_lock_on(
    accounts: Accounts, clock: MovableClock
) -> None:
    accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    _guess_wrong(accounts, clock, "lea", 30)
    assert accounts.update_user(lea.id, UserPatch(display_name="Lea", role=Role.GUEST)).locked


def test_wrong_current_pins_count_towards_the_lock_too(
    accounts: Accounts, clock: MovableClock
) -> None:
    user, token = accounts.setup("c", "C", GOOD)
    _guess_wrong(accounts, clock, "c", 25)
    clock.at += WINDOW
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            accounts.change_pin(user, "0000", "5678", token, IP)
    with pytest.raises(AccountLockedError):
        accounts.change_pin(user, GOOD, "5678", token, IP)
    with pytest.raises(AccountLockedError):
        accounts.login("c", GOOD, IP)
    assert accounts.authenticate(token) is not None, "the open session goes on"


def test_parallel_wrong_pins_cannot_get_past_the_lock(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = SqliteRepository(open_database(tmp_path / "library.db"))
    hasher, clock = SlowCountingHasher(), MovableClock()
    accounts = Accounts(repo, hasher, clock)
    accounts.setup("c", "C", GOOD)
    _guess_wrong(accounts, clock, "c", 27)
    clock.at += WINDOW
    outcomes = _race(
        *(lambda n=n: accounts.login("c", f"{n:04d}", f"10.2.0.{n}") for n in range(40))
    )
    assert hasher.verified == 30, "three guesses were left before the lock, however they arrive"
    assert [type(o) for o in outcomes].count(InvalidCredentialsError) == 3
    assert [type(o) for o in outcomes].count(AccountLockedError) == 37
    assert _locked(accounts, "c")


def test_a_disabled_account_gets_no_free_guesses(accounts: Accounts, clock: MovableClock) -> None:
    accounts.setup("c", "C", GOOD)
    lea = accounts.create_user("lea", "Léa", GOOD, Role.MEMBER)
    accounts.update_user(lea.id, UserPatch(disabled=True))
    for _ in range(10):
        with pytest.raises(InvalidCredentialsError):
            accounts.login("lea", GOOD, IP)  # right PIN, but disabled: still counted
    with pytest.raises(TooManyAttemptsError):
        accounts.login("lea", GOOD, IP)


# --- an admin's patch is all or nothing --------------------------------------------------------


class MiscountingStore:
    """The real store, but the early last-admin check sees an admin who is about to go (what
    a concurrent demotion looks like): only the store's own check, in its transaction, is left."""

    def __init__(self, repo: SqliteRepository) -> None:
        self._repo = repo

    def __getattr__(self, name: str) -> object:
        return getattr(self._repo, name)

    def count_active_admins(self) -> int:
        return self._repo.count_active_admins() + 1


def test_a_refused_patch_changes_neither_the_pin_nor_the_sessions(
    repo: SqliteRepository, clock: MovableClock
) -> None:
    accounts = Accounts(MiscountingStore(repo), FakeHasher(), clock)  # type: ignore[arg-type]
    admin, token = accounts.setup("c", "C", GOOD)
    with pytest.raises(LastAdminError):
        accounts.update_user(admin.id, UserPatch(role=Role.MEMBER, pin="5678"))
    assert accounts.authenticate(token) == admin, "still signed in, still an admin"
    accounts.login("c", GOOD, IP)
    with pytest.raises(InvalidCredentialsError):
        accounts.login("c", "5678", IP)
