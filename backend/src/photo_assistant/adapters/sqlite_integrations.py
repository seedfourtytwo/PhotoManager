"""SQLite storage for the integrations: AI log, remote-source config, inboxes, device tokens.

Kept apart from ``SqliteRepository`` so these features can land independently. Give it its own
connection to the same database file (WAL mode lets both work side by side).
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

from photo_assistant.domain.model import Source
from photo_assistant.domain.remote_source import RemoteConfig, RemoteConfigError
from photo_assistant.ports.ai import AICall
from photo_assistant.ports.upload import Device

RCLONE_KIND = "rclone"
INBOX_KIND = "inbox"


class _Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def _one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            cur.row_factory = sqlite3.Row
            row: sqlite3.Row | None = cur.fetchone()
            return row

    def _all(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            cur.row_factory = sqlite3.Row
            return cur.fetchall()

    def _write(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)


def _source(row: sqlite3.Row) -> Source:
    return Source(row["id"], row["label"], row["root"], bool(row["enabled"]), row["kind"])


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

    def recent(self, limit: int) -> list[dict[str, object]]:
        rows = self._all("SELECT * FROM ai_log ORDER BY id DESC LIMIT ?", (limit,))
        return [
            {
                "id": r["id"],
                "capability": r["capability"],
                "model": r["model"],
                "attempt": r["attempt"],
                "ok": bool(r["ok"]),
                "duration_ms": r["duration_ms"],
                "error": r["error"],
                "request": json.loads(r["request_json"]),
                "response": json.loads(r["response_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


class SqliteRemoteSources(_Store):
    def add_remote_source(self, label: str, config: RemoteConfig, staging_root: Path) -> int:
        # The root must be unique and depends on the id: insert a placeholder, then set it.
        with self._lock:
            cur = self._write(
                "INSERT INTO source (kind, label, root, config_json) VALUES (?, ?, ?, ?)",
                (RCLONE_KIND, label, f"rclone-pending:{uuid.uuid4().hex}", "{}"),
            )
            source_id = int(cur.lastrowid or 0)
            self._write(
                "UPDATE source SET root = ?, config_json = ? WHERE id = ?",
                (str(staging_root / str(source_id)), json.dumps(config.to_mapping()), source_id),
            )
        return source_id

    def remote_config(self, source_id: int) -> RemoteConfig | None:
        row = self._one("SELECT kind, config_json FROM source WHERE id = ?", (source_id,))
        if row is None or row["kind"] != RCLONE_KIND:
            return None
        data = json.loads(row["config_json"] or "{}")
        if not isinstance(data, dict):
            raise RemoteConfigError("the remote source's settings are damaged; add it again")
        return RemoteConfig.from_mapping(data)

    def set_root(self, source_id: int, root: str) -> None:
        self._write("UPDATE source SET root = ? WHERE id = ?", (root, source_id))


class SqliteInboxes(_Store):
    def ensure_inbox_source(self, user_id: int, root: str) -> Source:
        with self._lock:
            row = self._one(
                "SELECT s.* FROM inbox i JOIN source s ON s.id = i.source_id WHERE i.user_id = ?",
                (user_id,),
            )
            if row is None:
                return self._create(user_id, root)
            if row["root"] != root:  # the data root was moved: follow it
                self._write("UPDATE source SET root = ? WHERE id = ?", (root, row["id"]))
                row = self._one("SELECT * FROM source WHERE id = ?", (row["id"],))
                assert row is not None
            return _source(row)

    def _create(self, user_id: int, root: str) -> Source:
        cur = self._write(
            "INSERT INTO source (kind, label, root) VALUES (?, ?, ?)",
            (INBOX_KIND, f"Uploads (user {user_id})", root),
        )
        source_id = int(cur.lastrowid or 0)
        self._write("INSERT INTO inbox (user_id, source_id) VALUES (?, ?)", (user_id, source_id))
        row = self._one("SELECT * FROM source WHERE id = ?", (source_id,))
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
