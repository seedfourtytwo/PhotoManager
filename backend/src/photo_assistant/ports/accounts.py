"""Ports for accounts: password hashing and the account/session store."""

from datetime import datetime
from typing import Protocol

from photo_assistant.domain.access import Role, User


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool:
        """False for a wrong password; never raises for one."""
        ...


class UsernameTakenError(ValueError):
    """Another account already uses that user name (names ignore case)."""


class NotFirstUserError(ValueError):
    """First-run setup lost a race: accounts exist already."""


class NoActiveAdminError(ValueError):
    """The change would leave the library without an active admin (nothing was changed)."""


class AccountStore(Protocol):
    # users
    def count_users(self) -> int: ...
    def add_user(self, username: str, display_name: str, password_hash: str, role: Role) -> User:
        """Raises UsernameTakenError."""
        ...

    def add_first_admin(self, username: str, display_name: str, password_hash: str) -> User:
        """Atomically: create the first account (an admin) and give it the ownerless sources.
        Raises NotFirstUserError if any account exists (concurrent setups: one wins)."""
        ...

    def get_user(self, user_id: int) -> User | None: ...
    def find_user_by_username(self, username: str) -> tuple[User, str] | None:
        """The user and their password hash."""
        ...

    def list_users(self) -> list[User]: ...
    def update_user(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        role: Role | None = None,
        disabled: bool | None = None,
        password_hash: str | None = None,
    ) -> None:
        """One transaction; raises NoActiveAdminError (and changes nothing) if afterwards no
        active admin is left. None leaves a value as it is."""
        ...

    def set_pin_hash(self, user_id: int, password_hash: str) -> None: ...
    def count_active_admins(self) -> int: ...

    # sessions
    def add_session(self, token_hash: str, user_id: int, now: datetime) -> None: ...
    def session_user(self, token_hash: str) -> tuple[User, datetime] | None:
        """The session's user and when the session was last used."""
        ...

    def touch_session(self, token_hash: str, now: datetime) -> None: ...
    def delete_session(self, token_hash: str) -> None: ...
    def delete_sessions_of(self, user_id: int, keep: str | None = None) -> None:
        """End every session of the user except the one whose token hash is ``keep``."""
        ...

    def revoke_devices_of(self, user_id: int, now: datetime) -> None:
        """Revoke every device token of the user (they must create new ones)."""
        ...

    # failed logins (rate limit)
    def record_login_attempt(self, username: str, ip: str, at: datetime, since: datetime) -> bool:
        """Atomically: False (and nothing recorded) if this name already has too many failures
        from this address after ``since``; otherwise count one more, at ``at``, and True."""
        ...

    def clear_login_failures(self, username: str, ip: str) -> None: ...
    def clear_all_login_failures(self, username: str) -> None:
        """Every address's failures for this username, in any letter case."""
        ...
