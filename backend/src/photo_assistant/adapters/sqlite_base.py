"""Shared plumbing for the SQLite adapter: one connection, one lock, small query helpers.

The repository is split by area into mixins (accounts, library queries, albums, …) that all
inherit this base, so they share the connection and the lock and compose into one object.
"""

import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

Params = Sequence[object] | Mapping[str, object]


class SqliteBase:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _one(self, sql: str, params: Params = ()) -> sqlite3.Row | None:
        with self._lock:
            row: sqlite3.Row | None = self._conn.execute(sql, params).fetchone()
            return row

    def _all(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _write(self, sql: str, params: Params = ()) -> int:
        """Run one statement; returns the new row id (0 when none)."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            return int(cur.lastrowid or 0)

    def _count(self, sql: str, params: Params = ()) -> int:
        """Run one statement; returns how many rows it changed."""
        with self._lock:
            return int(self._conn.execute(sql, params).rowcount)

    def _scalar(self, sql: str, params: Params = ()) -> int:
        row = self._one(sql, params)
        return int(row[0]) if row is not None and row[0] is not None else 0

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """All or nothing. Not re-entrant: callers inside must use the plain helpers."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")
