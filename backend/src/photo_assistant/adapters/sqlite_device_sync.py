"""SQLite storage of "Keep on my phone" (migration 0031): rules per device, photos sent."""

import sqlite3
from collections.abc import Collection
from datetime import datetime

from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.device_sync import SyncKind, SyncMode, SyncRule, SyncTarget

_REF_COLUMN = {SyncKind.ALBUM: "album_id", SyncKind.PERSON: "person_id"}


def _rule(row: sqlite3.Row) -> SyncRule:
    kind = SyncKind(row["kind"])
    ref = row[_REF_COLUMN[kind]] if kind in _REF_COLUMN else None
    return SyncRule(row["id"], SyncTarget(kind, ref, row["filter_json"]), SyncMode(row["mode"]))


class SqliteDeviceSync(SqliteBase):
    def sync_rules(self, device_id: int) -> list[SyncRule]:
        rows = self._all("SELECT * FROM sync_rule WHERE device_id = ? ORDER BY id", (device_id,))
        return [_rule(r) for r in rows]

    def put_sync_rule(
        self, device_id: int, target: SyncTarget, mode: SyncMode, now: datetime
    ) -> SyncRule:
        album = target.ref_id if target.kind is SyncKind.ALBUM else None
        person = target.ref_id if target.kind is SyncKind.PERSON else None
        key = "device_id = ? AND kind = ? AND COALESCE(album_id, person_id, filter_json) IS ?"
        with self._transaction():
            self._write(
                """INSERT INTO sync_rule
                       (device_id, kind, album_id, person_id, filter_json, mode, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (device_id, kind, COALESCE(album_id, person_id, filter_json))
                   DO UPDATE SET mode = excluded.mode""",
                (device_id, target.kind, album, person, target.filters, mode, now.isoformat()),
            )
            row = self._one(
                f"SELECT * FROM sync_rule WHERE {key}",
                (
                    device_id,
                    target.kind,
                    target.ref_id if target.ref_id is not None else target.filters,
                ),
            )
        assert row is not None
        return _rule(row)

    def delete_sync_rule(self, device_id: int, rule_id: int) -> bool:
        deleted = self._count(
            "DELETE FROM sync_rule WHERE id = ? AND device_id = ?", (rule_id, device_id)
        )
        return deleted == 1

    def sent_ids(self, device_id: int) -> set[int]:
        rows = self._all("SELECT asset_id FROM sync_sent WHERE device_id = ?", (device_id,))
        return {int(r["asset_id"]) for r in rows}

    def mark_sent(self, device_id: int, asset_ids: Collection[int], now: datetime) -> None:
        with self._transaction():
            for asset_id in asset_ids:
                self._write(
                    """INSERT INTO sync_sent (device_id, asset_id, sent_at) VALUES (?, ?, ?)
                       ON CONFLICT (device_id, asset_id)
                       DO UPDATE SET sent_at = excluded.sent_at""",
                    (device_id, asset_id, now.isoformat()),
                )

    def forget_sent(self, device_id: int) -> int:
        return self._count("DELETE FROM sync_sent WHERE device_id = ?", (device_id,))

    def record_sync(self, device_id: int, now: datetime) -> None:
        self._write("UPDATE device SET last_sync_at = ? WHERE id = ?", (now.isoformat(), device_id))
