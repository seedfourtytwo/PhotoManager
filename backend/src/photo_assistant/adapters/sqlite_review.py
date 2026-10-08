"""Review on SQLite: hold, list, release and discard held photos."""

from collections.abc import Sequence
from datetime import datetime

from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.adapters.sqlite_library import (
    ASSET_FROM,
    asset_columns,
    view_from_row,
    visibility,
)
from photo_assistant.domain.access import Viewer
from photo_assistant.ports.library import AssetView


def _in(ids: Sequence[int]) -> str:
    return ", ".join("?" for _ in ids)


class ReviewMixin(SqliteBase):
    def hold_asset(self, asset_id: int, reason: str, like: int | None) -> bool:
        changed = self._count(
            """UPDATE asset SET held_reason = ?, held_like = ?
               WHERE id = ? AND held_reason IS NULL AND reviewed_at IS NULL
                 AND trashed_at IS NULL""",
            (reason, like, asset_id),
        )
        return changed == 1

    def held_views(self, viewer: Viewer) -> list[AssetView]:
        visible, level, params = visibility(viewer, held=True)
        rows = self._all(
            f"""SELECT {asset_columns(level)} {ASSET_FROM} WHERE {visible}
                ORDER BY a.held_reason, a.taken_at DESC, a.id DESC""",
            params,
        )
        return [view_from_row(r) for r in rows]

    def count_held(self, viewer: Viewer) -> int:
        visible, _, params = visibility(viewer, held=True)
        return self._scalar(f"SELECT COUNT(*) FROM asset a WHERE {visible}", params)

    def release_assets(self, ids: Sequence[int], now: datetime) -> int:
        if not ids:
            return 0
        return self._count(
            f"""UPDATE asset SET held_reason = NULL, held_like = NULL, reviewed_at = ?
                WHERE held_reason IS NOT NULL AND trashed_at IS NULL AND id IN ({_in(ids)})""",
            (utc_text(now), *ids),
        )

    def discard_held(self, ids: Sequence[int], user_id: int, now: datetime) -> int:
        if not ids:
            return 0
        when = utc_text(now)
        return self._count(
            f"""UPDATE asset SET trashed_at = ?, trashed_by = ?, reviewed_at = ?,
                                 held_reason = NULL, held_like = NULL
                WHERE held_reason IS NOT NULL AND trashed_at IS NULL AND id IN ({_in(ids)})""",
            (when, user_id, when, *ids),
        )
