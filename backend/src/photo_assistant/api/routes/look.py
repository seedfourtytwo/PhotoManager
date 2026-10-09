"""An account's look (docs/adr/0001): each account chooses its mode, an admin sets the rest.

The bodies are taken as plain JSON and checked by ``domain/look.py``, the one place that
knows the sheet: a refusal is its sentence (422), not a framework's list of errors.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body

from photo_assistant.api.deps import ADMIN_ONLY, CurrentUser, ServicesDep
from photo_assistant.api.schemas import LookOut

router = APIRouter(prefix="/api", tags=["look"])

# Any JSON, `null` and a missing body included: the sheet's own rules answer all of them.
Sheet = Annotated[Any, Body()]


@router.get("/me/look")
def my_look(services: ServicesDep, user: CurrentUser) -> LookOut:
    return LookOut.of(services.accounts.look_of(user.id))


@router.put("/me/look")
def choose_my_mode(services: ServicesDep, user: CurrentUser, body: Sheet = None) -> LookOut:
    """``{"mode": …}`` and nothing else, for every role: it is how their own screen looks."""
    return LookOut.of(services.accounts.choose_mode(user, body))


@router.get("/admin/accounts/{user_id}/look", dependencies=ADMIN_ONLY)
def account_look(services: ServicesDep, user_id: int) -> LookOut:
    return LookOut.of(services.accounts.look_of(user_id))


@router.put("/admin/accounts/{user_id}/look", dependencies=ADMIN_ONLY)
def set_account_look(services: ServicesDep, user_id: int, body: Sheet = None) -> LookOut:
    """The whole sheet; a field left out goes back to its default, so ``{}`` resets."""
    return LookOut.of(services.accounts.set_look(user_id, body))
