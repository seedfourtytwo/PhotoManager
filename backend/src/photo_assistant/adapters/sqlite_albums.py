"""Albums: owner, members, ordered items (FEATURES 5.1, 5.2, 8.4).

Counts, covers and items are read through the visibility rule, so an album never shows a
photo its viewer may not see (e.g. someone else's private photo inside a shared album).
"""

import sqlite3
from collections.abc import Sequence
from datetime import datetime

from photo_assistant.adapters.sqlite_access import UnknownUserError
from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.adapters.sqlite_library import (
    ALBUM_VISIBLE,
    ASSET_FROM,
    asset_columns,
    view_from_row,
    visibility,
)
from photo_assistant.domain.access import AlbumRole, Viewer
from photo_assistant.ports.library import AlbumInfo, AssetView


def _info_sql(visible: str) -> str:
    """Albums you may see, with their visible photo count and cover (``visible``: the rule)."""
    shown = (
        "FROM album_item ai JOIN asset a ON a.id = ai.asset_id"
        f" WHERE ai.album_id = al.id AND {visible}"
    )
    return f"""SELECT q.*, (SELECT edit_version FROM asset WHERE id = q.cover) AS cover_version
FROM (
    SELECT al.*, am.role AS member_role,
        (SELECT COUNT(*) {shown}) AS n,
        COALESCE(
            (SELECT ai.asset_id {shown} AND ai.asset_id = al.cover_asset_id),
            (SELECT ai.asset_id {shown} ORDER BY ai.position LIMIT 1)
        ) AS cover
    FROM album al
    LEFT JOIN album_member am ON am.album_id = al.id AND am.user_id = :vis_uid
    WHERE {ALBUM_VISIBLE} AND (:album IS NULL OR al.id = :album)
) q ORDER BY q.updated_at DESC, q.id DESC"""


def _role(row: sqlite3.Row, viewer: Viewer) -> AlbumRole:
    if row["owner_id"] == viewer.user_id:
        return AlbumRole.OWNER
    if row["member_role"]:
        return AlbumRole(row["member_role"])
    return AlbumRole.EDITOR  # an admin who is not a member: admins may change everything


def _info(row: sqlite3.Row, viewer: Viewer) -> AlbumInfo:
    return AlbumInfo(
        id=row["id"],
        owner_id=row["owner_id"],
        title=row["title"],
        description=row["description"],
        cover_asset_id=row["cover"],
        cover_version=int(row["cover_version"] or 0),
        count=int(row["n"]),
        role=_role(row, viewer),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class AlbumsMixin(SqliteBase):
    def create_album(self, owner_id: int, title: str, description: str, now: datetime) -> int:
        return self._write(
            """INSERT INTO album (owner_id, title, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (owner_id, title, description, utc_text(now), utc_text(now)),
        )

    def _albums(self, viewer: Viewer, album_id: int | None) -> list[AlbumInfo]:
        visible, _, params = visibility(viewer)
        rows = self._all(_info_sql(visible), params | {"album": album_id})
        return [_info(r, viewer) for r in rows]

    def list_albums(self, viewer: Viewer) -> list[AlbumInfo]:
        return self._albums(viewer, None)

    def album_info(self, viewer: Viewer, album_id: int) -> AlbumInfo | None:
        found = self._albums(viewer, album_id)
        return found[0] if found else None

    def album_views(self, viewer: Viewer, album_id: int) -> list[AssetView]:
        visible, level, params = visibility(viewer)
        rows = self._all(
            f"""SELECT {asset_columns(level)} {ASSET_FROM}
                JOIN album_item ai ON ai.asset_id = a.id AND ai.album_id = :album
                WHERE {visible} ORDER BY ai.position, a.id""",
            params | {"album": album_id},
        )
        return [view_from_row(r) for r in rows]

    def album_asset_ids(self, album_id: int) -> list[int]:
        rows = self._all(
            "SELECT asset_id FROM album_item WHERE album_id = ? ORDER BY position, asset_id",
            (album_id,),
        )
        return [int(r["asset_id"]) for r in rows]

    def update_album(
        self,
        album_id: int,
        now: datetime,
        *,
        title: str | None = None,
        description: str | None = None,
        cover_asset_id: int | None = None,
    ) -> None:
        self._write(
            """UPDATE album SET title = COALESCE(?, title),
                   description = COALESCE(?, description),
                   cover_asset_id = COALESCE(?, cover_asset_id), updated_at = ?
               WHERE id = ?""",
            (title, description, cover_asset_id, utc_text(now), album_id),
        )

    def delete_album(self, album_id: int) -> None:
        with self._transaction():
            for table in ("album_item", "album_member"):
                self._conn.execute(f"DELETE FROM {table} WHERE album_id = ?", (album_id,))
            self._conn.execute("DELETE FROM album WHERE id = ?", (album_id,))

    def _touch(self, album_id: int, now: datetime) -> None:
        self._conn.execute(
            "UPDATE album SET updated_at = ? WHERE id = ?", (utc_text(now), album_id)
        )

    def _write_order(self, album_id: int, ordered: Sequence[int]) -> None:
        self._conn.executemany(
            "UPDATE album_item SET position = ? WHERE album_id = ? AND asset_id = ?",
            [(i, album_id, asset_id) for i, asset_id in enumerate(ordered)],
        )

    def add_album_items(
        self, album_id: int, asset_ids: Sequence[int], before: int | None, now: datetime
    ) -> int:
        """Insert just before the photo ``before`` (default, or not in the album: at the end);
        photos already in the album are skipped. Anchoring on a photo rather than an index
        keeps photos other members see but the caller doesn't in place (QA A15)."""
        with self._transaction():
            current = self.album_asset_ids(album_id)
            new = [i for i in dict.fromkeys(asset_ids) if i not in set(current)]
            at = current.index(before) if before in current else len(current)
            self._conn.executemany(
                "INSERT INTO album_item (album_id, asset_id, position) VALUES (?, ?, 0)",
                [(album_id, asset_id) for asset_id in new],
            )
            self._write_order(album_id, current[:at] + new + current[at:])
            self._touch(album_id, now)
        return len(new)

    def remove_album_items(self, album_id: int, asset_ids: Sequence[int], now: datetime) -> int:
        with self._transaction():
            removed = 0
            for asset_id in set(asset_ids):
                removed += self._conn.execute(
                    "DELETE FROM album_item WHERE album_id = ? AND asset_id = ?",
                    (album_id, asset_id),
                ).rowcount
            # the chosen cover is kept: it shows again if its photo comes back (an undo); a
            # cover that is not in the album is ignored when the summary is read
            self._touch(album_id, now)
        return removed

    def reorder_album(self, album_id: int, asset_ids: Sequence[int], now: datetime) -> None:
        """``asset_ids`` first, in that order; photos not listed keep their order after them.
        Raises ValueError for ids that are not in the album."""
        with self._transaction():
            current = self.album_asset_ids(album_id)
            unknown = set(asset_ids) - set(current)
            if unknown or len(set(asset_ids)) != len(asset_ids):
                raise ValueError("the order must list photos of this album, each once")
            rest = [i for i in current if i not in set(asset_ids)]
            self._write_order(album_id, [*asset_ids, *rest])
            self._touch(album_id, now)

    def album_members(self, album_id: int) -> list[tuple[int, AlbumRole]]:
        rows = self._all(
            "SELECT user_id, role FROM album_member WHERE album_id = ? ORDER BY user_id",
            (album_id,),
        )
        return [(int(r["user_id"]), AlbumRole(r["role"])) for r in rows]

    def set_album_members(
        self, album_id: int, members: Sequence[tuple[int, AlbumRole]], now: datetime
    ) -> None:
        with self._transaction():
            self._conn.execute("DELETE FROM album_member WHERE album_id = ?", (album_id,))
            for user_id, role in members:
                if not self._conn.execute("SELECT 1 FROM user WHERE id = ?", (user_id,)).fetchone():
                    raise UnknownUserError(f"no user with id {user_id}")
                self._conn.execute(
                    """INSERT INTO album_member (album_id, user_id, role) VALUES (?, ?, ?)
                       ON CONFLICT DO UPDATE SET role = excluded.role""",
                    (album_id, user_id, role.value),
                )
            self._touch(album_id, now)
