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
planner's statistics.
"""

import sqlite3
import threading
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from types import TracebackType

ConnectionHook = Callable[[sqlite3.Connection], None]


def migrations() -> list[tuple[int, str]]:
    folder = resources.files("photo_assistant.adapters") / "migrations"
    found = []
    for entry in folder.iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.read_text()))
    return sorted(found)


def _snapshot(conn: sqlite3.Connection, backup_dir: Path, version: int) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    target = sqlite3.connect(backup_dir / f"library-v{version}-{stamp}.db")
    with target:
        conn.backup(target)
    target.close()


def open_database(path: str | Path, backup_dir: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) and migrate. ``":memory:"`` is fine for tests."""
    is_file = str(path) != ":memory:"
    existed = is_file and Path(path).exists()
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if is_file:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    pending = [(n, sql) for n, sql in migrations() if n > current]
    if pending and existed and backup_dir is not None:
        _snapshot(conn, backup_dir, current)
    for number, sql in pending:
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
    if pending:
        conn.execute("ANALYZE")  # fresh statistics for the planner after schema changes
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


_WRAPPED: "weakref.WeakValueDictionary[int, Database]" = weakref.WeakValueDictionary()


class Database:
    def __init__(self, writer: sqlite3.Connection, path: Path | None) -> None:
        writer.row_factory = sqlite3.Row
        self.writer = writer
        self.lock = WriteLock()
        self._path = path
        self._local = threading.local()
        self._readers: list[sqlite3.Connection] = []
        self._hooks: list[ConnectionHook] = []
        self._guard = threading.Lock()
        self._closed = False

    @classmethod
    def open(cls, path: str | Path, backup_dir: Path | None = None) -> "Database":
        """Open and migrate the library database (see ``open_database``)."""
        conn = open_database(path, backup_dir)
        return cls(conn, None if str(path) == ":memory:" else Path(path))

    @classmethod
    def of(cls, conn: sqlite3.Connection) -> "Database":
        """The Database around a bare connection (tests, tools): one per connection, so
        stores handed the same connection still share one lock."""
        found = _WRAPPED.get(id(conn))
        if found is not None and found.writer is conn:
            return found
        row = conn.execute("PRAGMA database_list").fetchone()
        file = row[2] if row is not None else ""
        database = cls(conn, Path(file) if file else None)
        _WRAPPED[id(conn)] = database
        return database

    @property
    def path(self) -> Path | None:
        return self._path

    def add_hook(self, hook: ConnectionHook) -> None:
        """Run ``hook`` on every connection (e.g. load an extension), now and later."""
        with self._guard:
            self._hooks.append(hook)
            connections = [self.writer, *self._readers]
        for conn in connections:
            hook(conn)

    def _reader(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            uri = f"file:{self._path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            with self._guard:
                for hook in self._hooks:
                    hook(conn)
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
