"""Account administration (admin only), and the small directory every member may read."""

from fastapi import APIRouter, status

from photo_assistant.api.deps import ADMIN_ONLY, MemberUser, ServicesDep
from photo_assistant.api.schemas import DirectoryEntry, NewUser, UserOut, UserPatchIn
from photo_assistant.app.accounts import (
    UserPatch,
)
from photo_assistant.domain.access import Role

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/directory")
def directory(services: ServicesDep, user: MemberUser) -> list[DirectoryEntry]:
    """Names to share albums with (v1.1): any member sees the active accounts, an admin sees
    every account. Ids and display names only; guests can't share, so they get none."""
    everyone = services.accounts.list_users()
    shown = everyone if user.role is Role.ADMIN else [u for u in everyone if not u.disabled]
    return [DirectoryEntry(id=u.id, display_name=u.display_name) for u in shown]


@router.get("", dependencies=ADMIN_ONLY)
def list_users(services: ServicesDep) -> list[UserOut]:
    return [UserOut.of(u) for u in services.accounts.list_users()]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=ADMIN_ONLY)
def create_user(services: ServicesDep, body: NewUser) -> UserOut:
    """409 for a taken name, 422 for a bad one (account errors carry their status)."""
    user = services.accounts.create_user(body.username, body.display_name, body.password, body.role)
    return UserOut.of(user)


@router.patch("/{user_id}", dependencies=ADMIN_ONLY)
def update_user(services: ServicesDep, user_id: int, body: UserPatchIn) -> UserOut:
    patch = UserPatch(
        display_name=body.display_name,
        role=body.role,
        disabled=body.disabled,
        password=body.password,
    )
    return UserOut.of(services.accounts.update_user(user_id, patch))


@router.post("/{user_id}/unlock", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY)
def unlock_user(services: ServicesDep, user_id: int) -> None:
    """Clear the login rate limit for this account (v1.3); 404 for an unknown id."""
    services.accounts.unlock(user_id)
