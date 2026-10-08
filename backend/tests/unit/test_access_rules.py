"""Pure rules for accounts and access (FEATURES 8, 11.10; contract api-v1 conventions)."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.domain.access import (
    LOCK_AFTER_FAILED_PINS,
    MAX_FAILED_LOGINS,
    SESSION_IDLE_LIMIT,
    AlbumRole,
    Level,
    Role,
    Viewer,
    can_edit_album,
    leaves_no_admin,
    locks_account,
    pin_problem,
    session_expired,
    too_many_failures,
    username_problem,
)


def test_levels_are_ordered_and_named() -> None:
    assert Level.VIEW < Level.DOWNLOAD < Level.EDIT
    assert Level.parse("download") is Level.DOWNLOAD
    assert Level.EDIT.label == "edit"
    with pytest.raises(ValueError, match="access level"):
        Level.parse("owner")


@pytest.mark.parametrize(
    ("role", "cap"),
    [(Role.ADMIN, Level.EDIT), (Role.MEMBER, Level.EDIT), (Role.GUEST, Level.DOWNLOAD)],
)
def test_guests_never_get_more_than_download(role: Role, cap: Level) -> None:
    viewer = Viewer(1, role)
    assert viewer.level_cap is cap
    assert viewer.is_admin is (role is Role.ADMIN)


@pytest.mark.parametrize(
    ("album_role", "user_role", "allowed"),
    [
        (AlbumRole.OWNER, Role.MEMBER, True),
        (AlbumRole.EDITOR, Role.MEMBER, True),
        (AlbumRole.VIEWER, Role.MEMBER, False),
        (AlbumRole.EDITOR, Role.GUEST, False),
        (None, Role.MEMBER, False),
        (None, Role.ADMIN, True),
    ],
)
def test_who_may_change_an_album(
    album_role: AlbumRole | None, user_role: Role, allowed: bool
) -> None:
    assert can_edit_album(album_role, user_role) is allowed


@pytest.mark.parametrize("pin", ["0000", "1234", "9999"])
def test_a_pin_is_exactly_four_digits(pin: str) -> None:
    assert pin_problem(pin) is None


@pytest.mark.parametrize(
    "pin",
    [
        "",
        "123",
        "12345",
        "12a4",
        " 123",
        "1234 ",
        "12.4",
        "-123",
        "\u0661\u0662\u0663\u0664",
        "\uff11\uff12\uff13\uff14",
    ],
)
def test_anything_else_is_not_a_pin(pin: str) -> None:
    assert pin_problem(pin) == "PINs are exactly 4 digits"


@pytest.mark.parametrize("name", ["", "a b", "x" * 65, "üser", "semi;colon"])
def test_bad_usernames_are_refused(name: str) -> None:
    assert username_problem(name) is not None


@pytest.mark.parametrize("name", ["c", "Lea", "anne.marie", "bob_2", "x-y"])
def test_ordinary_usernames_are_fine(name: str) -> None:
    assert username_problem(name) is None


def test_the_last_active_admin_cannot_be_removed() -> None:
    assert leaves_no_admin(active_admins=1, target_is_active_admin=True, stays_admin=False)
    assert not leaves_no_admin(active_admins=2, target_is_active_admin=True, stays_admin=False)
    assert not leaves_no_admin(active_admins=1, target_is_active_admin=False, stays_admin=False)
    assert not leaves_no_admin(active_admins=1, target_is_active_admin=True, stays_admin=True)


def test_sessions_expire_after_thirty_idle_days() -> None:
    now = datetime(2026, 9, 29, 12, 0)
    assert timedelta(days=30) == SESSION_IDLE_LIMIT
    assert not session_expired(now - timedelta(days=29, hours=23), now)
    assert session_expired(now - timedelta(days=30, seconds=1), now)


def test_ten_failures_lock_the_door() -> None:
    assert MAX_FAILED_LOGINS == 10
    assert not too_many_failures(9)
    assert too_many_failures(10)


def test_thirty_failures_since_the_last_good_sign_in_lock_the_account() -> None:
    assert LOCK_AFTER_FAILED_PINS == 30
    assert not locks_account(29)
    assert locks_account(30)
    assert locks_account(31)
