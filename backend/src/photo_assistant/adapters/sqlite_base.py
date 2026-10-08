"""Shared plumbing for the SQLite adapter: the one ``Database`` (one writer and lock, a reader
per thread) and small query helpers.

The repository is split by area into mixins (accounts, library queries, albums, …) that all
inherit this base, so they share the process's one ``Database`` and compose into one object.
"""

import base64
import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.media_types import MediaKind
from photo_assistant.domain.model import Asset, Source
from photo_assistant.domain.recheck import Recheck

Params = Sequence[object] | Mapping[str, object]


def iso_text(value: datetime) -> str:
    """A timestamp as it is stored: exactly as given (a capture time is local, without a zone).
    Instants that are compared as strings go through ``sqlite_accounts.utc_text`` instead."""
    return value.isoformat()


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


def source_from_row(row: sqlite3.Row) -> Source:
    return Source(
        row["id"],
        row["label"],
        row["root"],
        bool(row["enabled"]),
        row["kind"],
        row["owner_id"],
        Recheck(row["recheck"]),
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
    """Shared helpers over the process's one ``Database``: writes and transactions on its
    writer under its lock, reads on this thread's reader (see sqlite_database.py)."""

    def __init__(self, db: Database | sqlite3.Connection) -> None:
        self._db = db if isinstance(db, Database) else Database.of(db)
        self._conn = self._db.writer
        self._lock = self._db.lock

    def close(self) -> None:
        self._db.close()

    def _one(self, sql: str, params: Params = ()) -> sqlite3.Row | None:
        with self._db.reading() as conn:
            row: sqlite3.Row | None = conn.execute(sql, params).fetchone()
            return row

    def _all(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        with self._db.reading() as conn:
            return conn.execute(sql, params).fetchall()

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
        """All or nothing; inside another transaction it joins that one."""
        with self._db.transaction():
            yield
