"""Whether "send to a device" is switched on in this running app.

Set once at start from ``PA_SEND_TO_DEVICE``. Nothing changes it afterwards except test
mode's reset (``routes/testing.py``, mounted only with ``PA_TEST_MODE``), so the browser
tests can try the feature on and off against one server.
"""

from fastapi import HTTPException, Request, status
from starlette.applications import Starlette


def switch(app: Starlette, on: bool) -> None:
    app.state.send_to_device = on


def switched_on(app: Starlette) -> bool:
    return bool(app.state.send_to_device)


def feature_on(request: Request) -> None:
    """Switched off, the feature does not exist: 404, like any address the app does not
    know, whoever asks. (Outside test mode its routes are not even mounted then.)"""
    if not switched_on(request.app):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
