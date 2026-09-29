"""Account administration (admin only)."""

from fastapi import APIRouter, HTTPException, status

from photo_assistant.api.deps import ADMIN_ONLY, ServicesDep
from photo_assistant.api.schemas import NewUser, UserOut, UserPatchIn
from photo_assistant.app.accounts import (
    AccountError,
    LastAdminError,
    NameTakenError,
    NotFoundError,
    UserPatch,
)

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=ADMIN_ONLY)


@router.get("")
def list_users(services: ServicesDep) -> list[UserOut]:
    return [UserOut.of(u) for u in services.accounts.list_users()]


@router.post("", status_code=status.HTTP_201_CREATED)
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


@router.patch("/{user_id}")
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
