"""Trash on SQLite: soft delete, restore, purge, remembered hashes."""

from collections.abc import Sequence
from datetime import datetime

from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_base import SqliteBase, asset_from_row
from photo_assistant.domain.model import Asset

# Rows that point at an asset, in the order they must go (foreign keys are on).
_DEPENDENTS = ("asset_source", "user_asset", "album_item", "edit_recipe", "date_change")


def _in(ids: Sequence[int]) -> str:
    return ", ".join("?" for _ in ids)


class TrashMixin(SqliteBase):
    def trash_assets(self, ids: Sequence[int], user_id: int, now: datetime) -> int:
        if not ids:
            return 0
        return self._count(
            f"""UPDATE asset SET trashed_at = ?, trashed_by = ?
                WHERE trashed_at IS NULL AND id IN ({_in(ids)})""",
            (utc_text(now), user_id, *ids),
        )

    def restore_assets(self, ids: Sequence[int]) -> int:
        if not ids:
            return 0
        return self._count(
            f"""UPDATE asset SET trashed_at = NULL, trashed_by = NULL
                WHERE trashed_at IS NOT NULL AND id IN ({_in(ids)})""",
            tuple(ids),
        )

    def purge_candidates(
        self, ids: Sequence[int] | None, trashed_before: datetime | None
    ) -> list[Asset]:
        sql = "SELECT * FROM asset WHERE trashed_at IS NOT NULL"
        params: list[object] = []
        if ids is not None:
            if not ids:
                return []
            sql += f" AND id IN ({_in(ids)})"
            params += ids
        if trashed_before is not None:
            sql += " AND trashed_at < ?"
            params.append(utc_text(trashed_before))
        return [asset_from_row(r) for r in self._all(sql + " ORDER BY id", params)]

    def purge_asset(self, asset: Asset, now: datetime) -> None:
        with self._transaction():
            for table in _DEPENDENTS:
                self._conn.execute(f"DELETE FROM {table} WHERE asset_id = ?", (asset.id,))
            self._conn.execute(
                "UPDATE album SET cover_asset_id = NULL WHERE cover_asset_id = ?", (asset.id,)
            )
            self._conn.execute(
                "UPDATE asset SET variant_of = NULL WHERE variant_of = ?", (asset.id,)
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO purged_hash (content_hash, purged_at) VALUES (?, ?)",
                (asset.content_hash, utc_text(now)),
            )
            self._conn.execute("DELETE FROM asset WHERE id = ?", (asset.id,))

    def is_purged_hash(self, content_hash: str) -> bool:
        return (
            self._one("SELECT 1 FROM purged_hash WHERE content_hash = ?", (content_hash,))
            is not None
        )
