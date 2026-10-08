"""Accounts, roles and access levels: the pure rules (FEATURES 8, 11.10).

Who may *see* what is computed in one SQL function in the repository (ARCHITECTURE §7);
these are the small decisions around it that don't need a database.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum

PIN_LENGTH = 4
MAX_FAILED_LOGINS = 10  # wrong PINs for one account, from any address, within the window
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
LOCK_AFTER_FAILED_PINS = 30  # wrong PINs since the account's last good sign-in, however slow
SESSION_IDLE_LIMIT = timedelta(days=30)

_USERNAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_PIN = re.compile(rf"[0-9]{{{PIN_LENGTH}}}")  # ASCII digits only: what a phone keypad types


class Role(StrEnum):
    ADMIN = "admin"  # everything: accounts, sources, access
    MEMBER = "member"
    GUEST = "guest"  # view + download only; never edits


class Level(IntEnum):
    """Access level on a source or asset. Ordered: a higher level includes the lower ones."""

    VIEW = 1
    DOWNLOAD = 2
    EDIT = 3

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, label: str) -> "Level":
        try:
            return cls[label.upper()]
        except KeyError:
            raise ValueError(f"unknown access level: {label!r}") from None


class AlbumRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class User:
    id: int
    username: str
    display_name: str
    role: Role
    disabled: bool = False
    locked: bool = False  # too many wrong PINs: no sign-in until an admin or a new PIN lifts it


@dataclass(frozen=True, slots=True)
class Viewer:
    """Whoever is asking: every library query is made on behalf of one."""

    user_id: int
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @property
    def level_cap(self) -> Level:
        return Level.DOWNLOAD if self.role is Role.GUEST else Level.EDIT

    @classmethod
    def of(cls, user: User) -> "Viewer":
        return cls(user.id, user.role)


@dataclass(frozen=True, slots=True)
class SourceAccess:
    everyone: Level | None
    users: tuple[tuple[int, Level], ...] = ()


INBOX_KIND = "inbox"


def default_source_access(kind: str, owner_id: int | None) -> SourceAccess:
    """Who may see a new source (contract): everyone may download a folder or remote source;
    an upload inbox is private to its owner, who may edit."""
    if kind == INBOX_KIND and owner_id is not None:
        return SourceAccess(None, ((owner_id, Level.EDIT),))
    return SourceAccess(Level.DOWNLOAD)


def can_edit_album(album_role: AlbumRole | None, user_role: Role) -> bool:
    if user_role is Role.GUEST:
        return False
    if user_role is Role.ADMIN:
        return True
    return album_role in (AlbumRole.OWNER, AlbumRole.EDITOR)


def pin_problem(pin: str) -> str | None:
    if not _PIN.fullmatch(pin):
        return f"PINs are exactly {PIN_LENGTH} digits"
    return None


def username_problem(username: str) -> str | None:
    if not _USERNAME.match(username):
        return "user names use 1 to 64 letters, digits, dots, dashes or underscores"
    return None


def leaves_no_admin(active_admins: int, target_is_active_admin: bool, stays_admin: bool) -> bool:
    """Would this change (demote, disable) remove the last active admin?"""
    return target_is_active_admin and not stays_admin and active_admins <= 1


def session_expired(last_seen: datetime, now: datetime) -> bool:
    return now - last_seen > SESSION_IDLE_LIMIT


def too_many_failures(recent_failures: int) -> bool:
    return recent_failures >= MAX_FAILED_LOGINS


def locks_account(failures_since_last_login: int) -> bool:
    """The hard stop: a 4-digit PIN has 10,000 values, and the 15-minute wait alone lets a
    patient guesser through all of them in days. Thirty in a row ends the guessing."""
    return failures_since_last_login >= LOCK_AFTER_FAILED_PINS
