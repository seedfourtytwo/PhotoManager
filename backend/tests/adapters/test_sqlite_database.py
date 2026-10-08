"""One library database per process (B16, B26): every store shares ONE writer connection and
ONE lock; reads use a read-only connection per thread (WAL), so they never wait for a write."""

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_backup_store import SqliteBackupStore
from photo_assistant.adapters.sqlite_database import (
    Database,
    NewerDatabaseError,
    migrations,
    open_library_database,
)
from photo_assistant.adapters.sqlite_integrations import SqliteAILog
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.ports.ai import AICall


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database.open(tmp_path / "library.db")
    yield database
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
    assert db.writer.execute("SELECT COUNT(*) FROM ai_log").fetchone()[0] == 4 * 25


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
    seen: list[object] = []
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


def test_a_failed_commit_does_not_leave_the_writer_inside_a_transaction(db: Database) -> None:
    """Left open, every later transaction() would silently join it and never commit."""
    repo = SqliteRepository(db)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"), db.transaction() as conn:
        conn.execute("PRAGMA defer_foreign_keys = ON")  # the check moves to COMMIT
        conn.execute("INSERT INTO inbox (user_id, source_id) VALUES (8, 9)")  # neither exists
        reached_the_commit = True
    assert reached_the_commit
    assert not db.writer.in_transaction
    repo.enqueue("after", {})
    other = sqlite3.connect(db.path)  # type: ignore[arg-type]
    assert other.execute("SELECT kind FROM job").fetchall() == [("after",)], "it was committed"
    assert other.execute("SELECT COUNT(*) FROM inbox").fetchone() == (0,)
    other.close()


def test_the_real_error_survives_when_sqlite_already_rolled_back(db: Database) -> None:
    """ROLLBACK with no transaction open raises too, and used to hide what went wrong."""
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"), db.transaction() as conn:
        conn.execute("INSERT INTO source (label, root) VALUES ('a', '/a')")
        conn.execute("INSERT OR ROLLBACK INTO source (label, root) VALUES ('b', '/a')")
    assert not db.writer.in_transaction


@pytest.mark.parametrize("folder", ["photos #1", "what? where", "100%20real", "plain"])
def test_reads_work_in_a_data_folder_with_url_characters_in_its_name(
    tmp_path: Path, folder: str
) -> None:
    """The reader is opened by URI: '#', '?' and '%XX' in the path must be escaped, or the
    read lands on another (new, empty) file."""
    root = tmp_path / folder
    root.mkdir()
    db = Database.open(root / "library.db")
    repo = SqliteRepository(db)
    repo.enqueue("x", {})
    seen: list[object] = []
    reader = threading.Thread(target=lambda: seen.extend(j["kind"] for j in repo.list_jobs()))
    reader.start()
    reader.join()
    assert [j["kind"] for j in repo.list_jobs()] == ["x"]
    assert seen == ["x"], "and from another thread's reader"
    db.close()
    strays = {p.name for p in tmp_path.rglob("*")} - {folder, "library.db"}
    assert strays <= {"library.db-wal", "library.db-shm"}, f"stray files: {strays}"


def test_a_database_from_a_newer_version_of_the_app_is_refused(tmp_path: Path) -> None:
    """Opening it anyway would skip, forever, any later migration that reuses its number."""
    path = tmp_path / "library.db"
    Database.open(path).close()
    newest = max(number for number, _ in migrations())
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {newest + 2}")
    conn.close()
    with pytest.raises(NewerDatabaseError) as refused:
        Database.open(path, backup_dir=tmp_path / "backups")
    message = str(refused.value)
    assert f"version {newest + 2}" in message and f"version {newest}" in message
    assert "update" in message.lower(), "it says what to do"
    assert not (tmp_path / "backups").exists(), "nothing was touched"
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == newest + 2
    conn.close()


def test_the_library_database_lives_in_the_data_root_with_its_snapshots_beside_it(
    tmp_path: Path,
) -> None:
    sqlite3.connect(tmp_path / "library.db").execute("CREATE TABLE legacy (x)").connection.commit()
    db = open_library_database(tmp_path)
    try:
        assert db.path == tmp_path / "library.db"
        assert db.writer.execute("PRAGMA user_version").fetchone()[0] >= 1
        assert len(list((tmp_path / "db-backups").glob("library-v0-*.db"))) == 1
    finally:
        db.close()
