"""Accounts: first-run setup, login with rate limit, sessions, PIN change, user admin.

Session tokens are random; only their SHA-256 is stored. A session ends after
``SESSION_IDLE_LIMIT`` without use, on logout, or when its user is disabled.
"""

import hashlib
import math
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from photo_assistant.domain.access import (
    FAILED_LOGIN_WINDOW,
    Role,
    User,
    leaves_no_admin,
    pin_problem,
    session_expired,
    username_problem,
)
from photo_assistant.domain.errors import ConflictError, InvalidError
from photo_assistant.domain.errors import NotFoundError as DomainNotFound
from photo_assistant.ports import Clock
from photo_assistant.ports.accounts import (
    AccountStore,
    NoActiveAdminError,
    NotFirstUserError,
    PasswordHasher,
    UsernameTakenError,
)

_TOUCH_EVERY = timedelta(minutes=1)  # don't write to the database on every request
_VERIFIES_AT_ONCE = 2  # an argon2 check holds its whole memory cost (64 MiB) while it runs


class AccountError(InvalidError):
    """A request about accounts that can't be done; the message says why (422 by default)."""


class InvalidCredentialsError(AccountError):
    status = 401

    def __init__(self) -> None:
        super().__init__("wrong PIN")


class TooManyAttemptsError(AccountError):
    status = 429

    def __init__(self, retry_at: datetime, now: datetime) -> None:
        minutes = max(1, math.ceil((retry_at - now) / timedelta(minutes=1)))
        super().__init__(
            f"too many wrong PINs; wait {minutes} minute{'' if minutes == 1 else 's'} and try "
            "again, or ask an admin to unlock this account"
        )


class AccountLockedError(AccountError):
    """No sign-in, right PIN or not, until an admin unlocks the account or it gets a new PIN.
    The message is shown to anyone at the login screen: it names the two ways out and nothing
    about the account."""

    status = 423

    def __init__(self) -> None:
        super().__init__(
            "this account is locked after too many wrong PINs; ask an admin to unlock it, "
            "or set a new PIN on the server with 'just set-pin'"
        )


class AlreadySetUpError(AccountError):
    status = ConflictError.status

    def __init__(self) -> None:
        super().__init__("this library already has accounts; log in instead")


class LastAdminError(AccountError):
    status = ConflictError.status

    def __init__(self) -> None:
        super().__init__("the library needs at least one active admin")


class NameTakenError(AccountError):
    status = ConflictError.status

    def __init__(self, username: str) -> None:
        super().__init__(f"the user name '{username}' is taken")


class NotFoundError(AccountError):
    status = DomainNotFound.status

    def __init__(self) -> None:
        super().__init__("no such user")


@dataclass(frozen=True, slots=True)
class UserPatch:
    display_name: str | None = None
    role: Role | None = None
    disabled: bool | None = None
    pin: str | None = None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_pin(pin: str) -> None:
    problem = pin_problem(pin)
    if problem:
        raise AccountError(problem)


def _check_new_account(username: str, pin: str) -> None:
    problem = username_problem(username)
    if problem:
        raise AccountError(problem)
    _check_pin(pin)


class Accounts:
    def __init__(self, store: AccountStore, hasher: PasswordHasher, clock: Clock) -> None:
        self._store = store
        self._hasher = hasher
        self._clock = clock
        self._verifying = threading.BoundedSemaphore(_VERIFIES_AT_ONCE)

    # --- first run -------------------------------------------------------------------------

    def needs_admin(self) -> bool:
        return self._store.count_users() == 0

    def setup(self, username: str, display_name: str, pin: str) -> tuple[User, str]:
        if not self.needs_admin():
            raise AlreadySetUpError()
        _check_new_account(username, pin)
        try:
            user = self._store.add_first_admin(
                username, display_name.strip() or username, self._hasher.hash(pin)
            )
        except NotFirstUserError as exc:  # another setup won the race
            raise AlreadySetUpError() from exc
        return user, self._start_session(user)

    # --- users -----------------------------------------------------------------------------

    def create_user(self, username: str, display_name: str, pin: str, role: Role) -> User:
        _check_new_account(username, pin)
        try:
            return self._store.add_user(
                username, display_name.strip() or username, self._hasher.hash(pin), role
            )
        except UsernameTakenError as exc:
            raise NameTakenError(username) from exc

    def list_users(self) -> list[User]:
        return self._store.list_users()

    def login_names(self) -> list[tuple[str, str]]:
        """(user name, display name) of every account that can log in: the login screen
        shows them to anyone who reaches it, so nothing else about an account is given."""
        return [(u.username, u.display_name) for u in self._store.list_users() if not u.disabled]

    def set_pin(self, username: str, pin: str) -> User:
        """A new PIN without the old one, for the command line (a forgotten PIN)."""
        found = self._store.find_user_by_username(username)
        if found is None:
            raise NotFoundError()
        return self.update_user(found[0].id, UserPatch(pin=pin))

    def get_user(self, user_id: int) -> User | None:
        return self._store.get_user(user_id)

    def update_user(self, user_id: int, patch: UserPatch) -> User:
        user = self._store.get_user(user_id)
        if user is None:
            raise NotFoundError()
        self._guard_last_admin(user, patch)
        if patch.pin is not None:
            _check_pin(patch.pin)
        try:  # the one step that can still be refused goes first, and writes the PIN with it
            self._store.update_user(
                user_id,
                display_name=patch.display_name,
                role=patch.role,
                disabled=patch.disabled,
                password_hash=None if patch.pin is None else self._hasher.hash(patch.pin),
            )
        except NoActiveAdminError as exc:  # a concurrent change got past the early check
            raise LastAdminError() from exc
        if patch.pin is not None:
            # an admin reset is for a lost or leaked PIN: nothing the old one opened stays,
            # and the wrong tries at the old one no longer count (this lifts a lock, too)
            self._store.revoke_devices_of(user_id, self._clock.now())
            self._store.forgive_wrong_pins(user.username)
        if patch.pin is not None or patch.disabled:
            self._store.delete_sessions_of(user_id)
        updated = self._store.get_user(user_id)
        assert updated is not None
        return updated

    def unlock(self, user_id: int) -> None:
        """Lift the 15-minute wait and the lock on this account, and start its count of wrong
        PINs again: for the person who mistyped their PIN too often."""
        user = self._store.get_user(user_id)
        if user is None:
            raise NotFoundError()
        self._store.forgive_wrong_pins(user.username)

    def _guard_last_admin(self, user: User, patch: UserPatch) -> None:
        is_active_admin = user.role is Role.ADMIN and not user.disabled
        stays = (patch.role in (None, Role.ADMIN)) and not patch.disabled
        if leaves_no_admin(self._store.count_active_admins(), is_active_admin, stays):
            raise LastAdminError()

    # --- sessions --------------------------------------------------------------------------

    def login(self, username: str, pin: str, ip: str) -> tuple[User, str]:
        found = self._store.find_user_by_username(username)
        if found is None:
            # the login screen lists every account name, so who exists is no secret: an
            # unknown name costs no hash and leaves no row
            raise InvalidCredentialsError()
        user, pin_hash = found
        if not self._guess(username, pin_hash, pin, ip) or user.disabled:
            raise InvalidCredentialsError()
        self._store.forgive_wrong_pins(username)
        return user, self._start_session(user)

    def _guess(self, username: str, pin_hash: str, pin: str, ip: str) -> bool:
        """One counted try at a PIN: is it right? The try is counted *before* the PIN is
        checked, so guesses sent at the same moment can't all get in under the limits; the
        caller clears the count when the try turns out right. Tries are counted per account,
        whatever address they come from. Raises TooManyAttemptsError, AccountLockedError."""
        now = self._clock.now()
        tried = self._store.record_login_attempt(username, ip, now, now - FAILED_LOGIN_WINDOW)
        if tried.locked:
            raise AccountLockedError()
        if tried.retry_at is not None:
            raise TooManyAttemptsError(tried.retry_at, now)
        with self._verifying:
            return self._hasher.verify(pin_hash, pin)

    def _start_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self._store.add_session(_token_hash(token), user.id, self._clock.now())
        return token

    def authenticate(self, token: str) -> User | None:
        """The user behind a session cookie, or None (unknown, expired, disabled)."""
        key = _token_hash(token)
        found = self._store.session_user(key)
        if found is None:
            return None
        user, last_seen = found
        now = self._clock.now()
        if user.disabled or session_expired(last_seen, now):
            self._store.delete_session(key)
            return None
        if now - last_seen > _TOUCH_EVERY:
            self._store.touch_session(key, now)
        return user

    def logout(self, token: str) -> None:
        self._store.delete_session(_token_hash(token))

    def change_pin(self, user: User, current: str, new: str, keep_token: str, ip: str) -> None:
        """Every other session of this user ends (a thief's included); ``keep_token``, the
        session making the change, stays signed in. A wrong current PIN counts as a wrong
        PIN at login does: an open session is no way to guess the PIN without limit."""
        found = self._store.find_user_by_username(user.username)
        if found is None or not self._guess(user.username, found[1], current, ip):
            raise InvalidCredentialsError()
        self._store.forgive_wrong_pins(user.username)
        _check_pin(new)
        self._store.set_pin_hash(user.id, self._hasher.hash(new))
        self._store.delete_sessions_of(user.id, keep=_token_hash(keep_token))
