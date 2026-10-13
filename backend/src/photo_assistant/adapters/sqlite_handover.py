"""SQLite storage for hand-overs ("send to a device"), on the library's one ``Database``.

Times are stored as UTC text (``utc_text``) so that "has it run out" is a comparison SQLite
makes itself, inside the one statement that collects or cancels.
"""

import json
import sqlite3
from datetime import datetime

from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.handover import Handover
from photo_assistant.ports.handover import NewHandover

# still waiting at the given time: not cancelled, collections left, not run out
_WAITING = "cancelled_at IS NULL AND redemptions < max_redemptions AND expires_at > ?"


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _handover(row: sqlite3.Row) -> Handover:
    return Handover(
        id=row["id"],
        created_by=row["created_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        asset_ids=tuple(json.loads(row["asset_ids"])),
        byte_size=row["byte_size"],
        encrypted=bool(row["encrypted"]),
        details_removed=bool(row["details_removed"]),
        max_redemptions=row["max_redemptions"],
        redemptions=row["redemptions"],
        redeemed_at=_time(row["redeemed_at"]),
        redeemed_from=row["redeemed_from"],
        redeemed_agent=row["redeemed_agent"],
        cancelled_at=_time(row["cancelled_at"]),
    )


class SqliteHandovers(SqliteBase):
    def add_handover(self, new: NewHandover) -> Handover:
        handover_id = self._write(
            """INSERT INTO handover (token_hash, created_by, created_at, expires_at, asset_ids,
                                     byte_size, encrypted, details_removed, max_redemptions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new.token_hash,
                new.created_by,
                utc_text(new.created_at),
                utc_text(new.expires_at),
                json.dumps(list(new.asset_ids)),
                new.byte_size,
                int(new.encrypted),
                int(new.details_removed),
                new.max_redemptions,
            ),
        )
        found = self.get_handover(handover_id)
        assert found is not None
        return found

    def handover_by_token_hash(self, token_hash: str) -> tuple[Handover, str] | None:
        row = self._one("SELECT * FROM handover WHERE token_hash = ?", (token_hash,))
        return None if row is None else (_handover(row), str(row["token_hash"]))

    def get_handover(self, handover_id: int) -> Handover | None:
        row = self._one("SELECT * FROM handover WHERE id = ?", (handover_id,))
        return None if row is None else _handover(row)

    def list_handovers(self, created_by: int | None, limit: int) -> list[Handover]:
        rows = self._all(
            """SELECT * FROM handover WHERE (:by IS NULL OR created_by = :by)
               ORDER BY id DESC LIMIT :limit""",
            {"by": created_by, "limit": limit},
        )
        return [_handover(r) for r in rows]

    def redeem_handover(
        self, handover_id: int, now: datetime, client: str, agent: str | None
    ) -> bool:
        at = utc_text(now)
        changed = self._count(
            f"""UPDATE handover
                SET redemptions = redemptions + 1, redeemed_at = ?, redeemed_from = ?,
                    redeemed_agent = ?
                WHERE id = ? AND {_WAITING}""",
            (at, client, agent, handover_id, at),
        )
        return changed == 1

    def cancel_handover(self, handover_id: int, now: datetime) -> bool:
        at = utc_text(now)
        changed = self._count(
            f"UPDATE handover SET cancelled_at = ? WHERE id = ? AND {_WAITING}",
            (at, handover_id, at),
        )
        return changed == 1

    def prune_handovers(self, before: datetime) -> int:
        return self._count("DELETE FROM handover WHERE created_at < ?", (utc_text(before),))
