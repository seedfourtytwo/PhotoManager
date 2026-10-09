"""Sources without an owner (folders imported before any admin existed) go to the first
admin, however that admin comes to be: the rule is the accounts use case's, not a caller's.

And a store that registers sources is given the one registry; it does not build its own."""

from datetime import datetime

import pytest

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_integrations import SqliteInboxes, SqliteRemoteSources
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.accounts import Accounts, UserPatch
from photo_assistant.domain.access import Role
from tests.factories import NOW

PIN = "1234"


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(Database.open(":memory:"))


@pytest.fixture
def accounts(repo: SqliteRepository) -> Accounts:
    return Accounts(repo, FakeHasher(), FixedClock())


def _owners(repo: SqliteRepository) -> list[int | None]:
    return [s.owner_id for s in repo.list_sources()]


def test_the_first_admin_made_with_create_user_gets_the_ownerless_sources(
    accounts: Accounts, repo: SqliteRepository
) -> None:
    repo.add_source("Old", "/old")
    repo.add_source("Older", "/older")

    admin = accounts.create_user("c", "C", PIN, Role.ADMIN)

    assert _owners(repo) == [admin.id, admin.id]


def test_a_member_created_first_takes_nothing_and_the_admin_after_takes_all(
    accounts: Accounts, repo: SqliteRepository
) -> None:
    repo.add_source("Old", "/old")

    accounts.create_user("lea", "Lea", PIN, Role.MEMBER)
    assert _owners(repo) == [None], "only an admin owns what nobody added"
    admin = accounts.create_user("c", "C", PIN, Role.ADMIN)

    assert _owners(repo) == [admin.id]


def test_a_later_admin_takes_nothing_over(accounts: Accounts, repo: SqliteRepository) -> None:
    first = accounts.create_user("c", "C", PIN, Role.ADMIN)
    mine = repo.add_source("Mine", "/mine", first.id)
    late = repo.add_source("Imported from the command line", "/late")

    accounts.create_user("second", "Second", PIN, Role.ADMIN)

    assert _owners(repo) == [first.id, first.id], "also the late one: to the FIRST admin"
    assert {mine.id, late.id} == {s.id for s in repo.list_sources()}


def test_sources_wait_while_the_only_admin_is_disabled(
    accounts: Accounts, repo: SqliteRepository
) -> None:
    """The first admin who can log in, as migration 0023 chose."""
    first = accounts.create_user("c", "C", PIN, Role.ADMIN)
    second = accounts.create_user("d", "D", PIN, Role.ADMIN)
    accounts.update_user(first.id, UserPatch(disabled=True))
    repo.add_source("Late", "/late")

    assert accounts.give_ownerless_sources_to_first_admin() == 1

    assert _owners(repo) == [second.id]


def test_with_no_admin_the_sources_stay_ownerless(
    accounts: Accounts, repo: SqliteRepository
) -> None:
    repo.add_source("Old", "/old")
    assert accounts.give_ownerless_sources_to_first_admin() == 0
    assert _owners(repo) == [None]


@pytest.mark.parametrize("store", [SqliteRemoteSources, SqliteInboxes])
def test_a_store_that_registers_sources_must_be_given_the_registry(
    store: type, repo: SqliteRepository
) -> None:
    with pytest.raises(TypeError):
        store(repo._db)
    assert store(repo._db, repo)._sources is repo
