"""Test mode only (``PA_TEST_MODE=1``): reset the library to a named snapshot between E2E tests.

Mounted only in test mode, which ``create_app`` refuses unless the server listens on and answers
to loopback names only; each request must also come from this machine. Snapshots are plain
SQLite copies in ``<data root>/test-snapshots/<name>.db`` made by ``scripts/e2e_seed.py``.
"""

import ipaddress
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from photo_assistant.api.deps import ServicesDep
from photo_assistant.api.send_switch import switch

router = APIRouter(prefix="/__test", tags=["test mode"], include_in_schema=False)

LOOPBACK_NAMES = {"localhost"}


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class ResetIn(BaseModel):
    users: Literal["seed", "none"] = "seed"
    # "Send to a device" for the test that follows; left out, it is off as the product ships
    send: bool = False


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(request: Request, services: ServicesDep, body: ResetIn) -> Response:
    if request.client is None or not is_loopback(request.client.host):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "test mode answers this machine only")
    snapshot = services.settings.data_root.expanduser() / "test-snapshots" / f"{body.users}.db"
    if not snapshot.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no snapshot '{body.users}'")
    running = services.worker.is_running
    services.worker.stop()
    try:
        services.repo.restore_from(snapshot)
    finally:
        if running:
            services.worker.start()
    switch(request.app, body.send)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
