"""SQLite storage for the integrations: AI log, remote-source config, inboxes, device tokens.

Kept apart from ``SqliteRepository`` so these features can land independently; built on the
same ``Database`` (one writer, one lock) as every other store.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.domain.access import INBOX_KIND
from photo_assistant.domain.model import Source
from photo_assistant.domain.remote_source import (
    PROTON,
    RCLONE,
    RemoteConfig,
    RemoteConfigError,
)
from photo_assistant.ports import SourceRegistry
from photo_assistant.ports.ai import AICall
from photo_assistant.ports.upload import Device

REMOTE_KINDS = (RCLONE, PROTON)  # a remote source's kind is its provider
# who may see a new source is one domain rule (access.default_source_access), applied by the
# repository's add_source: remote sources like any folder, an inbox private to its owner


class _Store:
    """On the process's one ``Database``: its writer and lock, per-thread readers."""

    def __init__(self, db: Database | sqlite3.Connection) -> None:
        self._db = db if isinstance(db, Database) else Database.of(db)
        self._conn = self._db.writer
        self._lock = self._db.lock

    def _one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with self._db.reading() as conn:
            cur = conn.execute(sql, params)
            cur.row_factory = sqlite3.Row
            row: sqlite3.Row | None = cur.fetchone()
            return row

    def _all(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._db.reading() as conn:
            cur = conn.execute(sql, params)
            cur.row_factory = sqlite3.Row
            return cur.fetchall()

    def _write(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Several writes as one; inside another transaction it joins that one."""
        with self._db.transaction():
            yield


def _source(row: sqlite3.Row) -> Source:
    return Source(
        row["id"], row["label"], row["root"], bool(row["enabled"]), row["kind"], row["owner_id"]
    )


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SqliteAILog(_Store):
    def record(self, call: AICall) -> None:
        self._write(
            """INSERT INTO ai_log (capability, model, attempt, ok, duration_ms, error,
                                   request_json, response_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                call.capability,
                call.model,
                call.attempt,
                int(call.ok),
                call.duration_ms,
                call.error,
                json.dumps(call.request),
                json.dumps(call.response),
            ),
        )

    def prune(self, before: datetime) -> int:
        """Delete the calls logged before then; returns how many."""
        return self._write(
            # created_at is written by SQLite: compare in its own format
            "DELETE FROM ai_log WHERE created_at < strftime('%Y-%m-%dT%H:%M:%fZ', ?)",
            (before.astimezone(UTC).isoformat(),),
        ).rowcount


class _SourceCreator(_Store):
    """A store that registers sources through the one ``SourceRegistry`` (B17)."""

    def __init__(
        self, db: Database | sqlite3.Connection, sources: SourceRegistry | None = None
    ) -> None:
        super().__init__(db)
        # default: the repository on the same Database (one writer, one lock)
        from photo_assistant.adapters.sqlite_repository import SqliteRepository

        self._sources: SourceRegistry = sources or SqliteRepository(self._db)


class SqliteRemoteSources(_SourceCreator):
    def add_remote_source(
        self, label: str, config: RemoteConfig, staging_root: Path, owner_id: int
    ) -> int:
        """A source of its provider's kind, pulled into ``staging/<its id>`` (default access).

        It has an owner like a folder source: "private" compares the marker with the owner,
        so on an ownerless source the mark would hide the photo from nobody."""
        return self._sources.add_source(
            label,
            lambda source_id: str(staging_root / str(source_id)),
            owner_id,
            kind=config.provider,
            config=config.to_mapping(),
        ).id

    def remote_config(self, source_id: int) -> RemoteConfig | None:
        row = self._one("SELECT kind, config_json FROM source WHERE id = ?", (source_id,))
        if row is None or row["kind"] not in REMOTE_KINDS:
            return None
        data = json.loads(row["config_json"] or "{}")
        if not isinstance(data, dict):
            raise RemoteConfigError("the remote source's settings are damaged; add it again")
        return RemoteConfig.from_mapping(data)

    def set_root(self, source_id: int, root: str) -> None:
        self._write("UPDATE source SET root = ? WHERE id = ?", (root, source_id))


class SqliteInboxes(_SourceCreator):
    def ensure_inbox_source(self, user_id: int, root: str) -> Source:
        with self._lock:
            row = self._one(
                "SELECT s.* FROM inbox i JOIN source s ON s.id = i.source_id WHERE i.user_id = ?",
                (user_id,),
            )
            if row is None:
                with self._transaction():
                    return self._create(user_id, root)
            if row["root"] != root:  # the data root was moved: follow it
                self._write("UPDATE source SET root = ? WHERE id = ?", (root, row["id"]))
                row = self._one("SELECT * FROM source WHERE id = ?", (row["id"],))
                assert row is not None
            return _source(row)

    def _create(self, user_id: int, root: str) -> Source:
        """Inside the caller's transaction: the source and its inbox row, or neither."""
        name = self._one("SELECT display_name FROM user WHERE id = ?", (user_id,))
        label = f"Uploads ({name['display_name'] if name else f'user {user_id}'})"
        source = self._sources.add_source(label, root, user_id, kind=INBOX_KIND)
        self._write("INSERT INTO inbox (user_id, source_id) VALUES (?, ?)", (user_id, source.id))
        row = self._one("SELECT * FROM source WHERE id = ?", (source.id,))
        assert row is not None
        return _source(row)


class SqliteDevices(_Store):
    @staticmethod
    def _device(row: sqlite3.Row) -> Device:
        created = _time(row["created_at"])
        assert created is not None
        return Device(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            platform=row["platform"],
            created_at=created,
            last_used_at=_time(row["last_used_at"]),
            revoked_at=_time(row["revoked_at"]),
        )

    def add_device(
        self, user_id: int, name: str, platform: str, token_hash: str, now: datetime
    ) -> Device:
        cur = self._write(
            """INSERT INTO device (user_id, name, platform, token_hash, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, name, platform, token_hash, now.isoformat()),
        )
        row = self._one("SELECT * FROM device WHERE id = ?", (cur.lastrowid,))
        assert row is not None
        return self._device(row)

    def list_devices(self, user_id: int) -> list[Device]:
        rows = self._all("SELECT * FROM device WHERE user_id = ? ORDER BY id", (user_id,))
        return [self._device(r) for r in rows]

    def revoke_device(self, user_id: int, device_id: int, now: datetime) -> bool:
        cur = self._write(
            """UPDATE device SET revoked_at = ?
               WHERE id = ? AND user_id = ? AND revoked_at IS NULL""",
            (now.isoformat(), device_id, user_id),
        )
        return cur.rowcount == 1

    def user_for_token_hash(self, token_hash: str, now: datetime) -> int | None:
        with self._lock:
            row = self._one(
                "SELECT id, user_id FROM device WHERE token_hash = ? AND revoked_at IS NULL",
                (token_hash,),
            )
            if row is None:
                return None
            self._write(
                "UPDATE device SET last_used_at = ? WHERE id = ?", (now.isoformat(), row["id"])
            )
            return int(row["user_id"])
