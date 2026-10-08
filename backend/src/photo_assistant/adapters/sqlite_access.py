"""Source ownership and access lists (FEATURES 8.2)."""

from collections.abc import Sequence

from photo_assistant.adapters.sqlite_base import SqliteBase, source_from_row
from photo_assistant.adapters.sqlite_library import SOURCE_VISIBLE, visibility
from photo_assistant.domain.access import Level, SourceAccess, Viewer
from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.model import Source


class UnknownUserError(InvalidError):
    """An access list or album membership names an account that does not exist."""


class AccessMixin(SqliteBase):
    def _grant(self, source_id: int, access: SourceAccess) -> None:
        """A new source's access list (inside ``add_source``'s transaction)."""
        rows: list[tuple[int | None, Level]] = list(access.users)
        if access.everyone is not None:
            rows.append((None, access.everyone))
        for user_id, level in rows:
            self._write(
                "INSERT INTO source_access (source_id, user_id, level) VALUES (?, ?, ?)",
                (source_id, user_id, int(level)),
            )

    def get_access(self, source_id: int) -> tuple[Level | None, list[tuple[int, Level]]]:
        rows = self._all(
            "SELECT user_id, level FROM source_access WHERE source_id = ? ORDER BY user_id",
            (source_id,),
        )
        everyone = next((Level(r["level"]) for r in rows if r["user_id"] is None), None)
        users = [(int(r["user_id"]), Level(r["level"])) for r in rows if r["user_id"] is not None]
        return everyone, users

    def set_access(
        self, source_id: int, everyone: Level | None, users: Sequence[tuple[int, Level]]
    ) -> None:
        """Replace the access list. Raises UnknownUserError for an unknown account."""
        entries: list[tuple[int | None, Level]] = [(uid, level) for uid, level in users]
        if everyone is not None:
            entries.append((None, everyone))
        with self._transaction():
            self._conn.execute("DELETE FROM source_access WHERE source_id = ?", (source_id,))
            for user_id, level in entries:
                if (
                    user_id is not None
                    and not self._conn.execute(
                        "SELECT 1 FROM user WHERE id = ?", (user_id,)
                    ).fetchone()
                ):
                    raise UnknownUserError(f"no user with id {user_id}")
                self._conn.execute(
                    """INSERT INTO source_access (source_id, user_id, level) VALUES (?, ?, ?)
                       ON CONFLICT DO UPDATE SET level = excluded.level""",
                    (source_id, user_id, int(level)),
                )

    def set_source_owner(self, source_id: int, owner_id: int) -> None:
        if not self._one("SELECT 1 FROM user WHERE id = ?", (owner_id,)):
            raise UnknownUserError(f"no user with id {owner_id}")
        self._write("UPDATE source SET owner_id = ? WHERE id = ?", (owner_id, source_id))

    def sources_for(self, viewer: Viewer) -> list[tuple[Source, int]]:
        """Sources this viewer may see, each with how many of its photos they can see."""
        visible, _, params = visibility(viewer)
        rows = self._all(
            f"""SELECT s.*, (SELECT COUNT(DISTINCT x.asset_id) FROM asset_source x
                    JOIN asset a ON a.id = x.asset_id
                   WHERE x.source_id = s.id AND {visible}) AS n
                FROM source s WHERE {SOURCE_VISIBLE} ORDER BY s.id""",
            params,
        )
        return [(source_from_row(r), int(r["n"])) for r in rows]
