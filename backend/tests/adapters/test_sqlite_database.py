"""One library database per process (B16, B26): every store shares ONE writer connection and
ONE lock; reads use a read-only connection per thread (WAL), so they never wait for a write."""

import threading
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_backup_store import SqliteBackupStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_integrations import SqliteAILog
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.ports.ai import AICall


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database.open(tmp_path / "library.db")
    yield database  # type: ignore[misc]
    database.close()


def test_stores_built_on_one_database_share_its_writer_and_lock(db: Database) -> None:
    repo, log, backups = SqliteRepository(db), SqliteAILog(db), SqliteBackupStore(db)
    assert repo._conn is log._conn is backups._conn is db.writer
    assert repo._lock is log._lock is backups._lock is db.lock


def test_concurrent_transactions_from_several_stores_never_interleave(db: Database) -> None:
    """Two locks on one connection let two threads BEGIN on it at once ("cannot start a
    transaction within a transaction") — the bug of the old per-store locks."""
    repo, log = SqliteRepository(db), SqliteAILog(db)
    errors: list[BaseException] = []
    start = threading.Barrier(8)

    def work(n: int) -> None:
        try:
            start.wait()
            for i in range(25):
                if n % 2:
                    repo.enqueue_once(f"kind-{n}-{i}")
                else:
                    log.record(AICall("caption", "m", {}, {}, True, 1, None, 1))
        except BaseException as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(repo.list_jobs()) == 4 * 25
    assert len(log.recent(1000)) == 4 * 25


def test_reads_do_not_wait_for_a_write_in_progress(db: Database) -> None:
    repo = SqliteRepository(db)
    repo.enqueue("before", {})
    in_transaction, release = threading.Event(), threading.Event()

    def slow_write() -> None:
        with repo._transaction():
            repo._conn.execute("INSERT INTO job (kind, payload_json) VALUES ('during', '{}')")
            in_transaction.set()
            release.wait(5)

    writer = threading.Thread(target=slow_write)
    writer.start()
    assert in_transaction.wait(5)
    seen: list[str] = []
    reader = threading.Thread(target=lambda: seen.extend(j["kind"] for j in repo.list_jobs()))
    reader.start()
    reader.join(2)
    finished_while_writing = not reader.is_alive()
    release.set()
    writer.join()
    reader.join()
    assert finished_while_writing, "a read waited for the writer's lock"
    assert seen == ["before"], "it sees committed data only"
    assert [j["kind"] for j in repo.list_jobs()] == ["before", "during"]


def test_a_transaction_reads_its_own_writes(db: Database) -> None:
    repo = SqliteRepository(db)
    with repo._transaction():
        repo._conn.execute("INSERT INTO job (kind, payload_json) VALUES ('mine', '{}')")
        assert [j["kind"] for j in repo.list_jobs()] == ["mine"]


def test_an_in_memory_database_uses_its_one_connection_for_everything() -> None:
    db = Database.open(":memory:")
    repo = SqliteRepository(db)
    repo.enqueue("x", {})
    assert [j["kind"] for j in repo.list_jobs()] == ["x"]
    db.close()
    db.close()  # idempotent
