"""The library database, opened once per process and shared by every store (B16, B26).

- ONE writer connection behind ONE lock: every write and every transaction of every store
  (repository, integrations, ML, backups) goes through it, so two threads can never interleave
  statements of two transactions on one connection.
- A read-only connection per thread (WAL mode): reads run in parallel with each other and
  with the writer, and see committed data. A read made while this thread holds the write lock
  (inside a transaction) uses the writer, so it sees its own uncommitted rows.
- ``:memory:`` databases (tests) have just the one connection, used under the lock.

Migrations are numbered ``.sql`` files in ``migrations/``; ``PRAGMA user_version`` records the
last one applied. Before migrating an existing database, a consistent snapshot is written with
SQLite's online backup API (FEATURES 11.6); after migrating, ``ANALYZE`` refreshes the query
planner's statistics and all but the newest few of those snapshots are deleted.
"""

import logging
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from types import TracebackType

from photo_assistant.domain.library_paths import DATABASE_FILE

log = logging.getLogger(__name__)

SNAPSHOT_FOLDER = "db-backups"  # in the data root: the copies made before a migration

SNAPSHOTS_KEPT = 5  # pre-migration copies of the database; each is as big as the database
_SNAPSHOT_NAME = re.compile(r"library-v\d+-(\d{8}T\d{12})\.db")


def migrations() -> list[tuple[int, str]]:
    folder = resources.files("photo_assistant.adapters") / "migrations"
    found = []
    for entry in folder.iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.read_text()))
    return sorted(found)


class NewerDatabaseError(RuntimeError):
    """The database was migrated by a newer version of the app than the one opening it.

    Opening it anyway would run old code against a schema it does not know, and a later
    migration that happens to reuse the database's number would be skipped forever."""


def _snapshot(conn: sqlite3.Connection, backup_dir: Path, version: int) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    target = sqlite3.connect(backup_dir / f"library-v{version}-{stamp}.db")
    with target:
        conn.backup(target)
    target.close()


def _prune_snapshots(backup_dir: Path) -> None:
    """Delete all but the newest ``SNAPSHOTS_KEPT`` snapshots: only files named the way
    ``_snapshot`` names them, newest by the time in the name (not by version: as text, v10
    sorts before v9)."""
    ours = sorted(
        (found.group(1), entry)
        for entry in backup_dir.iterdir()
        if (found := _SNAPSHOT_NAME.fullmatch(entry.name))
    )
    for _, old in ours[:-SNAPSHOTS_KEPT]:
        try:
            old.unlink()
        except OSError as exc:  # an old copy that stays is no reason not to start
            log.warning("could not delete an old database snapshot: %s", exc)


def open_database(path: str | Path, backup_dir: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) and migrate. ``":memory:"`` is fine for tests."""
    is_file = str(path) != ":memory:"
    existed = is_file and Path(path).exists()
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if is_file:
        conn.execute("PRAGMA journal_mode = WAL")
        # In WAL mode a commit is safe from corruption without flushing the disk; NORMAL only
        # flushes at checkpoints (3 ms -> 0.03 ms per commit, each under the write lock). The
        # price: a power cut can lose the commits of the last seconds. Imports and jobs get
        # those back by scanning again; the few writes nothing brings back use ``durable``.
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    known = migrations()
    newest = max((n for n, _ in known), default=0)
    if current > newest:
        conn.close()
        raise NewerDatabaseError(
            f"The library database at {path} is at version {current}, but this copy of Photo "
            f"Assistant only knows up to version {newest}: a newer copy of the app has used "
            "this library. Update Photo Assistant and start it again; nothing was changed."
        )
    pending = [(n, sql) for n, sql in known if n > current]
    snapshot_dir = backup_dir if pending and existed else None
    if snapshot_dir is not None:
        _snapshot(conn, snapshot_dir, current)
    for number, sql in pending:
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
    if pending:
        conn.execute("ANALYZE")  # fresh statistics for the planner after schema changes
    if snapshot_dir is not None:  # only once the migration it guards has worked
        _prune_snapshots(snapshot_dir)
    return conn


class WriteLock:
    """The one write lock: re-entrant, and it knows whether *this* thread holds it."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._local = threading.local()

    def __enter__(self) -> "WriteLock":
        self._lock.acquire()
        self._local.depth = getattr(self._local, "depth", 0) + 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._local.depth -= 1
        self._lock.release()

    def held(self) -> bool:
        return bool(getattr(self._local, "depth", 0))


class Database:
    def __init__(self, writer: sqlite3.Connection, path: Path | None) -> None:
        writer.row_factory = sqlite3.Row
        self.writer = writer
        self.lock = WriteLock()
        self._path = path
        self._local = threading.local()
        self._readers: list[sqlite3.Connection] = []
        self._guard = threading.Lock()
        self._closed = False

    @classmethod
    def open(cls, path: str | Path, backup_dir: Path | None = None) -> "Database":
        """Open and migrate the library database (see ``open_database``)."""
        conn = open_database(path, backup_dir)
        return cls(conn, None if str(path) == ":memory:" else Path(path))

    @property
    def path(self) -> Path | None:
        return self._path

    def _reader(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            assert self._path is not None  # reading() sends in-memory databases to the writer
            # as_uri escapes '#', '?' and '%' in the folder name (they mean something in a URI)
            uri = f"{self._path.resolve().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            with self._guard:
                self._readers.append(conn)
            self._local.conn = conn
        return conn

    @contextmanager
    def reading(self) -> Iterator[sqlite3.Connection]:
        """The connection for a read: this thread's reader, or the writer (under the lock)
        inside a write or for an in-memory database."""
        if self._path is None or self.lock.held():
            with self.lock:
                yield self.writer
        else:
            yield self._reader()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """All or nothing on the writer (BEGIN IMMEDIATE). Nested calls join the outer
        transaction, so one store's write can be part of another's (e.g. an inbox row and
        the source it belongs to)."""
        with self.lock:
            if self.writer.in_transaction:
                yield self.writer
                return
            self.writer.execute("BEGIN IMMEDIATE")
            try:
                yield self.writer
                self.writer.execute("COMMIT")
            except BaseException:
                # a failed COMMIT leaves the transaction open; some errors (disk full, OR
                # ROLLBACK) have ended it already, and ROLLBACK would then hide the real one
                if self.writer.in_transaction:
                    self.writer.execute("ROLLBACK")
                raise

    @contextmanager
    def durable(self) -> Iterator[sqlite3.Connection]:
        """A transaction that is on the disk when it returns (one flush, ~3 ms): for a write
        that a power cut must not take back because nothing would redo it, e.g. forgetting a
        photo right before its files are deleted. Never inside another transaction: SQLite
        cannot change the flush level there, and the outer commit would not be flushed."""
        with self.lock:
            if self.writer.in_transaction:
                raise RuntimeError("a durable write cannot start inside a transaction")
            if self._path is None:  # in memory: nothing to flush
                with self.transaction() as conn:
                    yield conn
                return
            self.writer.execute("PRAGMA synchronous = FULL")
            try:
                with self.transaction() as conn:
                    yield conn
            finally:
                self.writer.execute("PRAGMA synchronous = NORMAL")

    def close(self) -> None:
        """Close every connection. Idempotent: every store sharing it may call it."""
        with self._guard:
            if self._closed:
                return
            self._closed = True
            readers, self._readers = self._readers, []
        for conn in readers:
            conn.close()
        with self.lock:
            self.writer.close()


def open_library_database(data_root: Path) -> Database:
    """THE way to open a library: its database file, with the pre-migration snapshots kept
    beside it in the data root."""
    return Database.open(data_root / DATABASE_FILE, backup_dir=data_root / SNAPSHOT_FOLDER)
