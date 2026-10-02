"""Accounts use case: setup, login, sessions, rate limit, user admin (FEATURES 8.1, 11.10)."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.accounts import (
    AccountError,
    Accounts,
    AlreadySetUpError,
    InvalidCredentialsError,
    LastAdminError,
    NotFoundError,
    TooManyAttemptsError,
    UserPatch,
)
from photo_assistant.domain.access import Role
from tests.factories import NOW

GOOD = "correct horse battery"


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
    assert repo.source_owner(source.id) == user.id


def test_passwords_are_hashed_and_checked(accounts: Accounts, repo: SqliteRepository) -> None:
    accounts.setup("c", "C", GOOD)
    stored = repo.find_user_by_username("C")
    assert stored is not None and stored[1] == f"hashed:{GOOD}", "usernames ignore case"
    user, token = accounts.login("c", GOOD, "10.0.0.1")
    assert accounts.authenticate(token) == user
    with pytest.raises(InvalidCredentialsError):
        accounts.login("c", "wrong password!", "10.0.0.1")
    with pytest.raises(InvalidCredentialsError):
        accounts.login("nobody", GOOD, "10.0.0.1")


def test_ten_failures_in_fifteen_minutes_block_that_user_from_that_address(
    accounts: Accounts, clock: MovableClock
) -> None:
    accounts.setup("c", "C", GOOD)
    for _ in range(10):
        with pytest.raises(InvalidCredentialsError):
            accounts.login("c", "wrong password!", "10.0.0.9")
    with pytest.raises(TooManyAttemptsError):
        accounts.login("c", GOOD, "10.0.0.9")
    accounts.login("c", GOOD, "10.0.0.2")  # another address is not blocked
    clock.at += timedelta(minutes=15, seconds=1)
    accounts.login("c", GOOD, "10.0.0.9")


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


def test_change_password_checks_the_current_one(accounts: Accounts) -> None:
    user, token = accounts.setup("c", "C", GOOD)
    _, other = accounts.login("c", GOOD, "2.2.2.2")
    with pytest.raises(InvalidCredentialsError):
        accounts.change_password(user, "not it at all", "another good one", token)
    with pytest.raises(AccountError, match="10 characters"):
        accounts.change_password(user, GOOD, "short", token)
    assert accounts.authenticate(other) is not None, "failed attempts change nothing"
    accounts.change_password(user, GOOD, "another good one", token)
    accounts.login("c", "another good one", "1.1.1.1")
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
    with pytest.raises(AccountError, match="10 characters"):
        accounts.create_user("tom", "Tom", "short", Role.GUEST)
    updated = accounts.update_user(lea.id, UserPatch(display_name="Lea M", role=Role.GUEST))
    assert updated.display_name == "Lea M" and updated.role is Role.GUEST
    accounts.update_user(lea.id, UserPatch(password="brand new secret"))
    accounts.login("lea", "brand new secret", "1.1.1.1")
    with pytest.raises(NotFoundError):
        accounts.update_user(999, UserPatch(disabled=True))
    assert admin.id != lea.id


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
