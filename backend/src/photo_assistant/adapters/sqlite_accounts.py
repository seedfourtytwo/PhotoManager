"""AccountStore on SQLite: users, sessions, failed logins."""

import sqlite3
from datetime import UTC, datetime

from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.access import Role, User
from photo_assistant.ports.accounts import UsernameTakenError


def utc_text(value: datetime) -> str:
    """Timestamps are stored as UTC ISO text, so they compare correctly as strings."""
    return value.astimezone(UTC).isoformat()


def _user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        role=Role(row["role"]),
        disabled=bool(row["disabled"]),
    )


class AccountsMixin(SqliteBase):
    # --- users -----------------------------------------------------------------------------

    def count_users(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM user")

    def add_user(self, username: str, display_name: str, password_hash: str, role: Role) -> User:
        try:
            user_id = self._write(
                """INSERT INTO user (username, display_name, password_hash, role)
                   VALUES (?, ?, ?, ?)""",
                (username, display_name, password_hash, role.value),
            )
        except sqlite3.IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        user = self.get_user(user_id)
        assert user is not None
        return user

    def get_user(self, user_id: int) -> User | None:
        row = self._one("SELECT * FROM user WHERE id = ?", (user_id,))
        return _user(row) if row else None

    def find_user_by_username(self, username: str) -> tuple[User, str] | None:
        row = self._one("SELECT * FROM user WHERE username = ?", (username,))
        return (_user(row), str(row["password_hash"])) if row else None

    def list_users(self) -> list[User]:
        return [_user(r) for r in self._all("SELECT * FROM user ORDER BY id")]

    def update_user(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        role: Role | None = None,
        disabled: bool | None = None,
    ) -> None:
        self._write(
            """UPDATE user SET display_name = COALESCE(?, display_name),
                   role = COALESCE(?, role), disabled = COALESCE(?, disabled)
               WHERE id = ?""",
            (
                display_name,
                role.value if role else None,
                None if disabled is None else int(disabled),
                user_id,
            ),
        )

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        self._write("UPDATE user SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def count_active_admins(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM user WHERE role = 'admin' AND disabled = 0")

    def claim_ownerless(self, user_id: int) -> None:
        with self._transaction():
            self._conn.execute("UPDATE source SET owner_id = ? WHERE owner_id IS NULL", (user_id,))
            self._conn.execute("UPDATE asset SET owner_id = ? WHERE owner_id IS NULL", (user_id,))

    # --- sessions --------------------------------------------------------------------------

    def add_session(self, token_hash: str, user_id: int, now: datetime) -> None:
        self._write(
            """INSERT INTO session (token_hash, user_id, created_at, last_seen_at)
               VALUES (?, ?, ?, ?)""",
            (token_hash, user_id, utc_text(now), utc_text(now)),
        )

    def session_user(self, token_hash: str) -> tuple[User, datetime] | None:
        row = self._one(
            """SELECT u.*, s.last_seen_at FROM session s JOIN user u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (token_hash,),
        )
        if row is None:
            return None
        return _user(row), datetime.fromisoformat(row["last_seen_at"])

    def touch_session(self, token_hash: str, now: datetime) -> None:
        self._write(
            "UPDATE session SET last_seen_at = ? WHERE token_hash = ?", (utc_text(now), token_hash)
        )

    def delete_session(self, token_hash: str) -> None:
        self._write("DELETE FROM session WHERE token_hash = ?", (token_hash,))

    def delete_sessions_of(self, user_id: int) -> None:
        self._write("DELETE FROM session WHERE user_id = ?", (user_id,))

    # --- failed logins ---------------------------------------------------------------------

    def add_login_failure(self, username: str, ip: str, at: datetime) -> None:
        self._write(
            "INSERT INTO login_failure (username, ip, at) VALUES (?, ?, ?)",
            (username, ip, utc_text(at)),
        )

    def count_login_failures(self, username: str, ip: str, since: datetime) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM login_failure WHERE username = ? AND ip = ? AND at > ?",
            (username, ip, utc_text(since)),
        )

    def clear_login_failures(self, username: str, ip: str) -> None:
        self._write("DELETE FROM login_failure WHERE username = ? AND ip = ?", (username, ip))
