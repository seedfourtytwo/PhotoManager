"""The writer does not flush the disk at every commit (WAL + synchronous NORMAL); the few
writes whose loss a rescan could not repair still do."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_backup_store import SqliteBackupStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Role
from photo_assistant.domain.backup import NewBackupTarget
from tests.factories import NOW, new_asset

NORMAL, FULL = 1, 2


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database.open(tmp_path / "library.db")
    yield database
    database.close()


def _synchronous(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA synchronous").fetchone()[0])


def _statements(db: Database) -> list[str]:
    seen: list[str] = []
    db.writer.set_trace_callback(seen.append)
    return seen


def _flushed(seen: list[str], statement: str) -> bool:
    """Was a statement starting like this run between a switch to FULL and the switch back?"""
    full = [n for n, sql in enumerate(seen) if sql == "PRAGMA synchronous = FULL"]
    normal = [n for n, sql in enumerate(seen) if sql == "PRAGMA synchronous = NORMAL"]
    at = [n for n, sql in enumerate(seen) if " ".join(sql.split()).startswith(statement)]
    return bool(at) and any(a < at[0] and at[-1] < b for a, b in zip(full, normal, strict=True))


def test_the_writer_runs_in_wal_mode_without_a_disk_flush_per_commit(db: Database) -> None:
    assert db.writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert _synchronous(db.writer) == NORMAL


def test_a_durable_write_flushes_and_then_goes_back_to_normal(db: Database) -> None:
    with db.durable() as conn:
        assert conn is db.writer and _synchronous(conn) == FULL
        assert conn.in_transaction
    assert _synchronous(db.writer) == NORMAL


def test_a_failed_durable_write_is_rolled_back_and_leaves_the_writer_normal(db: Database) -> None:
    with pytest.raises(RuntimeError, match="boom"), db.durable() as conn:
        conn.execute("INSERT INTO purged_hash (content_hash, purged_at) VALUES ('h', 'now')")
        raise RuntimeError("boom")
    assert _synchronous(db.writer) == NORMAL
    assert db.writer.execute("SELECT COUNT(*) FROM purged_hash").fetchone()[0] == 0


def test_a_durable_write_cannot_join_a_transaction_that_is_not_durable(db: Database) -> None:
    """SQLite cannot change the flush level inside a transaction: say so instead of
    committing without the flush the caller asked for."""
    with (
        db.transaction(),
        pytest.raises(RuntimeError, match="inside a transaction"),
        db.durable(),
    ):
        pass
    assert _synchronous(db.writer) == NORMAL


def test_an_in_memory_database_has_nothing_to_flush() -> None:
    database = Database.open(":memory:")
    with database.durable() as conn:
        conn.execute("INSERT INTO purged_hash (content_hash, purged_at) VALUES ('h', 'now')")
    assert database.writer.execute("SELECT COUNT(*) FROM purged_hash").fetchone()[0] == 1


def _target(tmp_path: Path) -> NewBackupTarget:
    return NewBackupTarget("Disk", str(tmp_path / "repo"), str(tmp_path / "backup.key"))


def test_a_new_backup_target_is_on_the_disk_when_it_is_answered(
    db: Database, tmp_path: Path
) -> None:
    """Its row is the only link between the repository and the key file it is locked with."""
    seen = _statements(db)
    SqliteBackupStore(db).add_target(_target(tmp_path), NOW)
    assert _flushed(seen, "INSERT INTO backup_target")


def test_the_owners_word_that_the_key_is_kept_is_on_the_disk(db: Database, tmp_path: Path) -> None:
    store = SqliteBackupStore(db)
    target = store.add_target(_target(tmp_path), NOW)
    seen = _statements(db)
    store.mark_key_saved(target.id, NOW)
    assert _flushed(seen, "UPDATE backup_target SET key_saved_at")
    assert store.get_target(target.id).key_saved_at == NOW  # type: ignore[union-attr]


def test_a_purge_is_on_the_disk_before_the_photos_files_are_deleted(db: Database) -> None:
    """Otherwise a power cut could bring back the row of a photo whose original is gone."""
    repo = SqliteRepository(db)
    asset_id = repo.add_asset(new_asset(1), NOW)
    user = repo.add_user("ck", "C", "hash", Role.ADMIN)
    repo.trash_assets([asset_id], user.id, NOW)
    (asset,) = repo.purge_candidates([asset_id], None)
    seen = _statements(db)

    assert repo.purge_asset(asset, datetime(2026, 1, 1)) is True
    assert _flushed(seen, "DELETE FROM asset WHERE id")
    assert _synchronous(db.writer) == NORMAL
