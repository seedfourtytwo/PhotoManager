"""Every error is ``{"detail": sentence}`` (contract conventions), from ONE handler (B21)."""

import pytest
from fastapi.testclient import TestClient

from photo_assistant.domain.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    InvalidError,
    NotFoundError,
    UnavailableError,
)


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFoundError, 404),
        (ForbiddenError, 403),
        (InvalidError, 422),
        (ConflictError, 409),
        (UnavailableError, 503),
        (DomainError, 400),
    ],
)
def test_domain_errors_become_their_status_with_the_message_as_detail(
    admin: TestClient, error: type[DomainError], status: int
) -> None:
    def boom() -> None:
        raise error("what happened, and what to do")

    admin.app.add_api_route("/api/__boom", boom)  # type: ignore[attr-defined]
    response = admin.get("/api/__boom")
    assert response.status_code == status
    assert response.json() == {"detail": "what happened, and what to do"}


def test_the_cross_site_guard_answers_in_json_too(admin: TestClient) -> None:
    response = admin.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"detail": "cross-site request refused"}


def test_account_errors_use_the_hierarchy(admin: TestClient) -> None:
    assert admin.patch("/api/users/999", json={"display_name": "x"}).json() == {
        "detail": "no such user"
    }
    me = admin.get("/api/auth/me").json()["id"]
    last = admin.patch(f"/api/users/{me}", json={"role": "member"})
    assert last.status_code == 409 and "admin" in last.json()["detail"]
    taken = admin.post(
        "/api/users",
        json={
            "username": "ADMIN",
            "display_name": "x",
            "password": "a long password!",
            "role": "member",
        },
    )
    assert taken.status_code == 409
