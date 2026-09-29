"""Consistent copies of the live library.db with SQLite's online backup API.

Copying a live SQLite file (plus its -wal) with cp/rsync/restic can capture a torn state; the
backup API copies a consistent point in time while the app keeps running. The copy is written
beside the destination and renamed into place, so a crash never leaves a half-written snapshot,
and it is switched to rollback-journal mode so it is one self-contained file.
"""

import os
import sqlite3
import uuid
from pathlib import Path

from photo_assistant.ports.backup import BackupError


def open_read_only(database: Path) -> sqlite3.Connection:
    """Open without ever writing to the file (works for WAL databases too)."""
    if not database.is_file():
        raise FileNotFoundError(f"no library database at {database}")
    uri = f"{database.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class SqliteSnapshotter:
    def __init__(self, database: Path) -> None:
        self._database = database

    def snapshot(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{uuid.uuid4().hex}.partial")
        try:
            self._copy(partial)
            partial.replace(destination)
        except sqlite3.Error as exc:
            raise BackupError(f"could not snapshot the library database: {exc}") from exc
        finally:
            partial.unlink(missing_ok=True)

    def _copy(self, partial: Path) -> None:
        source = open_read_only(self._database)
        try:
            target = sqlite3.connect(partial)
            try:
                source.backup(target)
                target.execute("PRAGMA journal_mode = DELETE")
                if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("the snapshot failed its integrity check")
            finally:
                target.close()
        finally:
            source.close()
        with partial.open("rb") as handle:
            os.fsync(handle.fileno())
