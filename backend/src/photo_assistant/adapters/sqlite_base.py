"""Shared plumbing for the SQLite adapter: one connection, one lock, small query helpers.

The repository is split by area into mixins (accounts, library queries, albums, …) that all
inherit this base, so they share the connection and the lock and compose into one object.
"""

import base64
import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime

from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.media_types import MediaKind
from photo_assistant.domain.model import Asset

Params = Sequence[object] | Mapping[str, object]


def asset_from_row(row: sqlite3.Row) -> Asset:
    return Asset(
        content_hash=row["content_hash"],
        kind=MediaKind(row["kind"]),
        mime_type=row["mime_type"],
        byte_size=row["byte_size"],
        width=row["width"],
        height=row["height"],
        taken_at=datetime.fromisoformat(row["taken_at"]),
        tz_offset_minutes=row["tz_offset_min"],
        date_source=DateSource(row["date_source"]),
        latitude=row["latitude"],
        longitude=row["longitude"],
        camera_make=row["camera_make"],
        camera_model=row["camera_model"],
        orientation=row["orientation"],
        library_path=row["library_path"],
        id=row["id"],
        imported_at=datetime.fromisoformat(row["imported_at"]),
        thumb_path=row["thumb_path"],
        preview_path=row["preview_path"],
        variant_of=row["variant_of"],
        thumb_size=(row["thumb_w"], row["thumb_h"]) if row["thumb_w"] else None,
    )


def encode_cursor(taken_at: str, asset_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([taken_at, asset_id]).encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        taken_at, asset_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return str(taken_at), int(asset_id)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid cursor: {cursor!r}") from exc


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
