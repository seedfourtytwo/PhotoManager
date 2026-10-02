"""Accounts: first-run setup, login with rate limit, sessions, password change, user admin.

Session tokens are random; only their SHA-256 is stored. A session ends after
``SESSION_IDLE_LIMIT`` without use, on logout, or when its user is disabled.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from photo_assistant.domain.access import (
    FAILED_LOGIN_WINDOW,
    Role,
    User,
    leaves_no_admin,
    password_problem,
    session_expired,
    too_many_failures,
    username_problem,
)
from photo_assistant.ports import Clock
from photo_assistant.ports.accounts import (
    AccountStore,
    NoActiveAdminError,
    NotFirstUserError,
    PasswordHasher,
    UsernameTakenError,
)

_TOUCH_EVERY = timedelta(minutes=1)  # don't write to the database on every request


class AccountError(ValueError):
    """A request about accounts that can't be done; the message says why."""


class InvalidCredentialsError(AccountError):
    def __init__(self) -> None:
        super().__init__("wrong user name or password")


class TooManyAttemptsError(AccountError):
    def __init__(self) -> None:
        super().__init__("too many failed logins; wait 15 minutes and try again")


class AlreadySetUpError(AccountError):
    def __init__(self) -> None:
        super().__init__("this library already has accounts; log in instead")


class LastAdminError(AccountError):
    def __init__(self) -> None:
        super().__init__("the library needs at least one active admin")


class NameTakenError(AccountError):
    def __init__(self, username: str) -> None:
        super().__init__(f"the user name '{username}' is taken")


class NotFoundError(AccountError):
    def __init__(self) -> None:
        super().__init__("no such user")


@dataclass(frozen=True, slots=True)
class UserPatch:
    display_name: str | None = None
    role: Role | None = None
    disabled: bool | None = None
    password: str | None = None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_password(password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise AccountError(problem)


def _check_new_account(username: str, password: str) -> None:
    problem = username_problem(username)
    if problem:
        raise AccountError(problem)
    _check_password(password)


class Accounts:
    def __init__(self, store: AccountStore, hasher: PasswordHasher, clock: Clock) -> None:
        self._store = store
        self._hasher = hasher
        self._clock = clock
        self._dummy_hash: str | None = None

    # --- first run -------------------------------------------------------------------------

    def needs_admin(self) -> bool:
        return self._store.count_users() == 0

    def setup(self, username: str, display_name: str, password: str) -> tuple[User, str]:
        if not self.needs_admin():
            raise AlreadySetUpError()
        _check_new_account(username, password)
        try:
            user = self._store.add_first_admin(
                username, display_name.strip() or username, self._hasher.hash(password)
            )
        except NotFirstUserError as exc:  # another setup won the race
            raise AlreadySetUpError() from exc
        return user, self._start_session(user)

    # --- users -----------------------------------------------------------------------------

    def create_user(self, username: str, display_name: str, password: str, role: Role) -> User:
        _check_new_account(username, password)
        try:
            return self._store.add_user(
                username, display_name.strip() or username, self._hasher.hash(password), role
            )
        except UsernameTakenError as exc:
            raise NameTakenError(username) from exc

    def list_users(self) -> list[User]:
        return self._store.list_users()

    def get_user(self, user_id: int) -> User | None:
        return self._store.get_user(user_id)

    def update_user(self, user_id: int, patch: UserPatch) -> User:
        user = self._store.get_user(user_id)
        if user is None:
            raise NotFoundError()
        self._guard_last_admin(user, patch)
        if patch.password is not None:
            _check_password(patch.password)
            self._store.set_password_hash(user_id, self._hasher.hash(patch.password))
            # an admin reset is for a lost or leaked password: nothing the old one opened stays
            self._store.delete_sessions_of(user_id)
            self._store.revoke_devices_of(user_id, self._clock.now())
        try:
            self._store.update_user(
                user_id, display_name=patch.display_name, role=patch.role, disabled=patch.disabled
            )
        except NoActiveAdminError as exc:  # a concurrent change got past the early check
            raise LastAdminError() from exc
        if patch.disabled:
            self._store.delete_sessions_of(user_id)
        updated = self._store.get_user(user_id)
        assert updated is not None
        return updated

    def _guard_last_admin(self, user: User, patch: UserPatch) -> None:
        is_active_admin = user.role is Role.ADMIN and not user.disabled
        stays = (patch.role in (None, Role.ADMIN)) and not patch.disabled
        if leaves_no_admin(self._store.count_active_admins(), is_active_admin, stays):
            raise LastAdminError()

    # --- sessions --------------------------------------------------------------------------

    def login(self, username: str, password: str, ip: str) -> tuple[User, str]:
        now = self._clock.now()
        since = now - FAILED_LOGIN_WINDOW
        if too_many_failures(self._store.count_login_failures(username, ip, since)):
            raise TooManyAttemptsError()
        found = self._store.find_user_by_username(username)
        if found is None:
            self._hasher.verify(self._dummy(), password)  # same work: don't reveal who exists
        if found is None or not self._hasher.verify(found[1], password) or found[0].disabled:
            self._store.add_login_failure(username, ip, now)
            raise InvalidCredentialsError()
        self._store.clear_login_failures(username, ip)
        return found[0], self._start_session(found[0])

    def _dummy(self) -> str:
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash(secrets.token_hex(16))
        return self._dummy_hash

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

    def change_password(self, user: User, current: str, new: str, keep_token: str) -> None:
        """Every other session of this user ends (a thief's included); ``keep_token``, the
        session making the change, stays signed in."""
        found = self._store.find_user_by_username(user.username)
        if found is None or not self._hasher.verify(found[1], current):
            raise InvalidCredentialsError()
        _check_password(new)
        self._store.set_password_hash(user.id, self._hasher.hash(new))
        self._store.delete_sessions_of(user.id, keep=_token_hash(keep_token))
