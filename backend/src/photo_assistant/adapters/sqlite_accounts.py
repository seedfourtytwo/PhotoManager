"""AccountStore on SQLite: users, sessions, failed logins."""

import sqlite3
from datetime import UTC, datetime

from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.access import Role, User, locks_account, too_many_failures
from photo_assistant.ports.accounts import (
    NoActiveAdminError,
    NotFirstUserError,
    PinTry,
    UsernameTakenError,
)


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
        locked=row["locked_at"] is not None,
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

    def add_first_admin(self, username: str, display_name: str, password_hash: str) -> User:
        with self._transaction():  # BEGIN IMMEDIATE: one setup at a time (QA A8)
            if self._conn.execute("SELECT 1 FROM user LIMIT 1").fetchone():
                raise NotFirstUserError("accounts exist already")
            user_id = int(
                self._conn.execute(
                    """INSERT INTO user (username, display_name, password_hash, role)
                       VALUES (?, ?, ?, 'admin')""",
                    (username, display_name, password_hash),
                ).lastrowid
                or 0
            )
            self._conn.execute("UPDATE source SET owner_id = ? WHERE owner_id IS NULL", (user_id,))
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
        password_hash: str | None = None,
    ) -> None:
        with self._transaction():  # the last-admin rule is checked inside (QA A8)
            self._conn.execute(
                """UPDATE user SET display_name = COALESCE(?, display_name),
                       role = COALESCE(?, role), disabled = COALESCE(?, disabled),
                       password_hash = COALESCE(?, password_hash)
                   WHERE id = ?""",
                (
                    display_name,
                    role.value if role else None,
                    None if disabled is None else int(disabled),
                    password_hash,
                    user_id,
                ),
            )
            admins = self._conn.execute(
                "SELECT COUNT(*) FROM user WHERE role = 'admin' AND disabled = 0"
            ).fetchone()[0]
            if admins == 0:
                raise NoActiveAdminError("the library needs at least one active admin")

    def set_pin_hash(self, user_id: int, password_hash: str) -> None:
        self._write("UPDATE user SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def count_active_admins(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM user WHERE role = 'admin' AND disabled = 0")

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

    def delete_sessions_of(self, user_id: int, keep: str | None = None) -> None:
        self._write(
            "DELETE FROM session WHERE user_id = ? AND token_hash IS NOT ?", (user_id, keep)
        )

    def prune_sessions(self, last_seen_before: datetime) -> int:
        """Delete sessions idle since before then: expired ones whose cookie never came back
        (a session is otherwise only deleted when it is presented again)."""
        return self._count(
            "DELETE FROM session WHERE last_seen_at < ?", (utc_text(last_seen_before),)
        )

    def revoke_devices_of(self, user_id: int, now: datetime) -> None:
        self._write(
            "UPDATE device SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now.isoformat(), user_id),
        )

    # --- failed logins ---------------------------------------------------------------------

    def record_login_attempt(self, username: str, ip: str, at: datetime, since: datetime) -> PinTry:
        # Both username columns are COLLATE NOCASE: "Lea" and "lea" are the same account.
        with self._transaction():  # check and count as one step: parallel guesses queue here
            account = self._conn.execute(
                "SELECT failed_pins, locked_at FROM user WHERE username = ?", (username,)
            ).fetchone()
            if account is not None and account["locked_at"] is not None:
                return PinTry(locked=True)
            recent, oldest = self._conn.execute(
                "SELECT COUNT(*), MIN(at) FROM login_failure WHERE username = ? AND at > ?",
                (username, utc_text(since)),
            ).fetchone()
            if too_many_failures(recent):
                # the oldest failure leaves the window first, and takes the block with it
                return PinTry(retry_at=datetime.fromisoformat(oldest) + (at - since))
            self._conn.execute(
                "INSERT INTO login_failure (username, ip, at) VALUES (?, ?, ?)",
                (username, ip, utc_text(at)),
            )
            if account is not None:
                # on the user row, not counted from login_failure: those rows are pruned daily
                failed = account["failed_pins"] + 1
                self._conn.execute(
                    "UPDATE user SET failed_pins = ?, locked_at = ? WHERE username = ?",
                    (failed, utc_text(at) if locks_account(failed) else None, username),
                )
            return PinTry()

    def forgive_wrong_pins(self, username: str) -> None:
        with self._transaction():
            self._conn.execute("DELETE FROM login_failure WHERE username = ?", (username,))
            self._conn.execute(
                "UPDATE user SET failed_pins = 0, locked_at = NULL WHERE username = ?",
                (username,),
            )

    def prune_login_failures(self, before: datetime) -> int:
        """Forget failures older than the lockout looks back: those of names that never log
        in successfully are otherwise kept forever."""
        return self._count("DELETE FROM login_failure WHERE at < ?", (utc_text(before),))
