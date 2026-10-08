"""First-run setup, the login screen's account names, login/logout, the current user, PIN change."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from photo_assistant.api.deps import SESSION_COOKIE, CurrentUser, ServicesDep
from photo_assistant.api.schemas import AccountName, Credentials, NewPin, SetupIn, UserOut
from photo_assistant.app.accounts import (
    InvalidCredentialsError,
)
from photo_assistant.domain.access import SESSION_IDLE_LIMIT

router = APIRouter(prefix="/api", tags=["auth"])


def _set_session(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_IDLE_LIMIT.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/setup")
def setup_state(services: ServicesDep) -> dict[str, bool]:
    return {"needs_admin": services.accounts.needs_admin()}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup(services: ServicesDep, body: SetupIn, request: Request, response: Response) -> UserOut:
    user, token = services.accounts.setup(body.username, body.display_name, body.pin)
    _set_session(request, response, token)
    return UserOut.of(user)


@router.get("/auth/accounts")
def accounts(services: ServicesDep) -> list[AccountName]:
    """Open, like login: the login screen offers the active accounts to pick from."""
    return [
        AccountName(username=username, display_name=display_name)
        for username, display_name in services.accounts.login_names()
    ]


@router.post("/auth/login")
def login(
    services: ServicesDep, body: Credentials, request: Request, response: Response
) -> UserOut:
    ip = request.client.host if request.client else "unknown"
    user, token = services.accounts.login(body.username, body.pin, ip)  # 401 / 429
    _set_session(request, response, token)
    return UserOut.of(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(services: ServicesDep, user: CurrentUser, request: Request) -> Response:
    services.accounts.logout(request.cookies.get(SESSION_COOKIE, ""))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)


@router.post("/auth/pin", status_code=status.HTTP_204_NO_CONTENT)
def change_pin(services: ServicesDep, user: CurrentUser, body: NewPin, request: Request) -> None:
    """Ends every other session of this user; this one stays signed in."""
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        services.accounts.change_pin(user, body.current_pin, body.new_pin, token)
    except InvalidCredentialsError as exc:  # signed in already: a wrong field, not a 401
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the current PIN is wrong") from exc
