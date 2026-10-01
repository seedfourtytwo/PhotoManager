"""Account administration (admin only), and the small directory every member may read."""

from fastapi import APIRouter, HTTPException, status

from photo_assistant.api.deps import ADMIN_ONLY, CurrentUser, ServicesDep
from photo_assistant.api.schemas import DirectoryEntry, NewUser, UserOut, UserPatchIn
from photo_assistant.app.accounts import (
    AccountError,
    LastAdminError,
    NameTakenError,
    NotFoundError,
    UserPatch,
)
from photo_assistant.domain.access import Role

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/directory")
def directory(services: ServicesDep, user: CurrentUser) -> list[DirectoryEntry]:
    """Names to share albums with (v1.1): any member sees the active accounts, an admin sees
    every account. Ids and display names only; guests can't share, so they get none."""
    if user.role is Role.GUEST:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "guests can't share albums")
    everyone = services.accounts.list_users()
    shown = everyone if user.role is Role.ADMIN else [u for u in everyone if not u.disabled]
    return [DirectoryEntry(id=u.id, display_name=u.display_name) for u in shown]


@router.get("", dependencies=ADMIN_ONLY)
def list_users(services: ServicesDep) -> list[UserOut]:
    return [UserOut.of(u) for u in services.accounts.list_users()]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=ADMIN_ONLY)
def create_user(services: ServicesDep, body: NewUser) -> UserOut:
    try:
        user = services.accounts.create_user(
            body.username, body.display_name, body.password, body.role
        )
    except NameTakenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return UserOut.of(user)


@router.patch("/{user_id}", dependencies=ADMIN_ONLY)
def update_user(services: ServicesDep, user_id: int, body: UserPatchIn) -> UserOut:
    patch = UserPatch(
        display_name=body.display_name,
        role=body.role,
        disabled=body.disabled,
        password=body.password,
    )
    try:
        return UserOut.of(services.accounts.update_user(user_id, patch))
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except LastAdminError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
