"""Ports for accounts: password hashing and the account/session store."""

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class PinTry:
    """The store's answer to one try at a PIN: go ahead and check it, or why not."""

    locked: bool = False  # the account is locked until an admin or a new PIN lifts it
    retry_at: datetime | None = None  # too many recent failures: when the next try is taken

    @property
    def allowed(self) -> bool:
        return not self.locked and self.retry_at is None


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

    def give_ownerless_sources_to_first_admin(self) -> int:
        """Every source without an owner goes to the first admin who can log in (lowest id,
        not disabled). Returns how many; 0, and nothing changes, while there is no such admin."""
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

    # wrong PINs (rate limit and account lock)
    def record_login_attempt(self, username: str, ip: str, at: datetime, since: datetime) -> PinTry:
        """Atomically: refuse (and record nothing) if the account is locked, or if this name
        already has too many failures after ``since`` from all addresses together. Otherwise
        count one more, at ``at``, both in the window and on the account's running count
        since its last good sign-in, locking the account when that count is used up."""
        ...

    def users_waiting(self, since: datetime) -> set[int]:
        """Ids of the accounts with too many failures after ``since``: their next try waits."""
        ...

    def forgive_wrong_pins(self, username: str) -> None:
        """Forget every counted try at this account's PIN (the name in any letter case) and
        lift its lock: after a right PIN, an admin's unlock, or a new PIN."""
        ...
