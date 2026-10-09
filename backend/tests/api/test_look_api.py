"""The look sheet over HTTP, per role (contract api-v1 "Look"; issue 11 acceptance): unknown
fields rejected, numbers clamped, a broken sheet falls back to the defaults; an account can
change only its mode; an admin can set any account's look."""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import BASE, add_user, refusal, services_of, user_id_of

DEFAULTS = {
    "theme": "safelight",
    "mode": "dark",
    "accentHue": None,
    "corners": None,
    "photoGap": None,
    "textScale": 1,
    "thumbSize": "medium",
    "showToday": True,
    "startPage": "today",
    "collectionsRows": ["people", "places", "albums"],
    "dockLabels": True,
}
WARM = {
    "theme": "album",
    "mode": "light",
    "accentHue": 30,
    "corners": 6,
    "photoGap": 4,
    "textScale": 1.15,
    "thumbSize": "large",
    "showToday": True,
    "startPage": "library",
    "collectionsRows": ["albums", "people"],
    "dockLabels": False,
}


def _look_url(admin: TestClient, username: str) -> str:
    return f"/api/admin/accounts/{user_id_of(admin, username)}/look"


def test_a_new_account_has_the_default_look(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    assert admin.get("/api/me/look").json() == DEFAULTS
    assert lea.get("/api/me/look").json() == DEFAULTS
    assert admin.get(_look_url(admin, "lea")).json() == DEFAULTS


def test_a_member_changes_their_mode_and_nothing_else_moves(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    assert admin.put(_look_url(admin, "lea"), json=WARM).status_code == 200

    changed = lea.put("/api/me/look", json={"mode": "system"})

    assert changed.status_code == 200
    assert changed.json() == {**WARM, "mode": "system"}
    assert lea.get("/api/me/look").json() == {**WARM, "mode": "system"}
    assert admin.get("/api/me/look").json() == DEFAULTS, "only her own account"


def test_a_guest_may_choose_their_mode_too(admin: TestClient) -> None:
    guest = add_user(admin, "gran", role="guest")
    assert guest.put("/api/me/look", json={"mode": "light"}).json()["mode"] == "light"


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "light", "accentHue": 200},
        {"theme": "album"},
        {"mode": "light", "css": "x"},
        {},
        ["light"],
        "light",
    ],
)
def test_a_member_cannot_send_any_other_field(admin: TestClient, body: object) -> None:
    lea = add_user(admin, "lea")
    status, answer = refusal(lea.put("/api/me/look", json=body))
    assert status == 422
    assert answer == {
        "detail": 'you can change only your mode: send {"mode": "dark"}, "light" or "system"; '
        "an admin sets the rest of your look"
    }
    assert lea.get("/api/me/look").json() == DEFAULTS


def test_a_member_cannot_send_an_unknown_mode(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    assert refusal(lea.put("/api/me/look", json={"mode": "sepia"})) == (
        422,
        {"detail": "'mode' must be one of: system, dark, light"},
    )


@pytest.mark.parametrize("role", ["member", "guest"])
def test_a_member_and_a_guest_cannot_read_or_set_another_accounts_look(
    admin: TestClient, role: str
) -> None:
    other = add_user(admin, "sam", role=role)
    for url in (_look_url(admin, "admin"), _look_url(admin, "sam")):  # not even their own
        assert other.get(url).status_code == 403
        assert other.put(url, json=WARM).status_code == 403
    assert admin.get("/api/me/look").json() == DEFAULTS
    assert other.get("/api/me/look").json() == DEFAULTS


def test_nobody_signed_in_gets_no_look(admin: TestClient) -> None:
    nobody = TestClient(admin.app, base_url=BASE)
    assert nobody.get("/api/me/look").status_code == 401
    assert nobody.put("/api/me/look", json={"mode": "light"}).status_code == 401
    assert nobody.get("/api/admin/accounts/1/look").status_code == 401
    assert nobody.put("/api/admin/accounts/1/look", json=WARM).status_code == 401


def test_an_admin_sets_any_accounts_look_and_that_account_gets_it(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    gran = add_user(admin, "gran", role="guest")

    saved = admin.put(_look_url(admin, "lea"), json=WARM)

    assert (saved.status_code, saved.json()) == (200, WARM)
    assert lea.get("/api/me/look").json() == WARM
    assert admin.get(_look_url(admin, "lea")).json() == WARM
    assert gran.get("/api/me/look").json() == DEFAULTS
    assert admin.put(_look_url(admin, "gran"), json={"textScale": 1.25}).status_code == 200
    assert gran.get("/api/me/look").json() == {**DEFAULTS, "textScale": 1.25}


def test_an_admin_sets_their_own_look(admin: TestClient) -> None:
    assert admin.put(_look_url(admin, "admin"), json={"accentHue": 200}).status_code == 200
    assert admin.get("/api/me/look").json() == {**DEFAULTS, "accentHue": 200}


def test_an_unknown_field_is_refused_and_nothing_is_stored(admin: TestClient) -> None:
    add_user(admin, "lea")
    url = _look_url(admin, "lea")
    assert admin.put(url, json=WARM).status_code == 200

    refused = admin.put(url, json={"mode": "dark", "css": "body{display:none}"})

    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("unknown look field 'css'; a look has only: theme")
    assert admin.get(url).json() == WARM


def test_numbers_are_clamped_on_the_way_in(admin: TestClient) -> None:
    sent = {"accentHue": 720, "corners": -5, "photoGap": 99, "textScale": 3}
    saved = admin.put(_look_url(admin, "admin"), json=sent)
    assert saved.status_code == 200
    assert saved.json() == {
        **DEFAULTS,
        "accentHue": 360,
        "corners": 0,
        "photoGap": 8,
        "textScale": 1.25,
    }


def test_hiding_today_starts_the_account_on_the_library(admin: TestClient) -> None:
    saved = admin.put(_look_url(admin, "admin"), json={"showToday": False, "startPage": "today"})
    assert (saved.json()["showToday"], saved.json()["startPage"]) == (False, "library")


def test_an_empty_sheet_resets_the_look(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    url = _look_url(admin, "lea")
    assert admin.put(url, json=WARM).status_code == 200
    assert admin.put(url, json={}).json() == DEFAULTS
    assert lea.get("/api/me/look").json() == DEFAULTS


@pytest.mark.parametrize(
    "stored", ["{not json", "[]", '{"css": "x"}', '{"textScale": "big"}', '{"theme": "gone"}']
)
def test_a_broken_stored_sheet_answers_the_defaults(admin: TestClient, stored: str) -> None:
    lea = add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    services_of(admin).repo.store_look(lea_id, stored)

    assert lea.get("/api/me/look").json() == DEFAULTS
    assert admin.get(f"/api/admin/accounts/{lea_id}/look").json() == DEFAULTS
    # and the way out of a broken sheet works: the account's own mode, the admin's save
    assert lea.put("/api/me/look", json={"mode": "light"}).json() == {**DEFAULTS, "mode": "light"}
    assert admin.put(f"/api/admin/accounts/{lea_id}/look", json=WARM).json() == WARM


def test_a_stored_field_that_no_longer_passes_costs_only_itself(admin: TestClient) -> None:
    """A theme removed in a later version: the account keeps its other choices, also after
    it changes its mode (which writes the sheet back)."""
    lea = add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    stored = '{"theme": "gone", "mode": "light", "accentHue": 200, "corners": 4, "css": "x"}'
    services_of(admin).repo.store_look(lea_id, stored)
    kept = {**DEFAULTS, "mode": "light", "accentHue": 200, "corners": 4}

    assert lea.get("/api/me/look").json() == kept
    assert admin.get(f"/api/admin/accounts/{lea_id}/look").json() == kept
    assert lea.put("/api/me/look", json={"mode": "system"}).json() == {**kept, "mode": "system"}
    assert lea.get("/api/me/look").json() == {**kept, "mode": "system"}


def test_a_half_is_rounded_up_and_a_number_beyond_every_float_is_clamped(
    admin: TestClient,
) -> None:
    body = '{"accentHue": 0.5, "corners": 2.5, "photoGap": 1e400, "textScale": 1.125}'
    saved = admin.put(
        _look_url(admin, "admin"), content=body, headers={"content-type": "application/json"}
    )
    assert saved.status_code == 200
    assert saved.json() == {
        **DEFAULTS,
        "accentHue": 1,
        "corners": 3,
        "photoGap": 8,
        "textScale": 1.13,
    }


def test_the_look_of_an_unknown_account_is_not_found(admin: TestClient) -> None:
    assert refusal(admin.get("/api/admin/accounts/999/look")) == (404, {"detail": "no such user"})
    assert admin.put("/api/admin/accounts/999/look", json=WARM).status_code == 404


@pytest.mark.parametrize("body", [[], "album", 3, None, [WARM]])
def test_a_sheet_that_is_not_an_object_is_refused(admin: TestClient, body: object) -> None:
    status, answer = refusal(admin.put(_look_url(admin, "admin"), json=body))
    assert (status, answer) == (422, {"detail": "a look is an object of named values"})
    assert admin.get("/api/me/look").json() == DEFAULTS


def test_a_disabled_accounts_look_can_still_be_set(admin: TestClient) -> None:
    add_user(admin, "lea")
    lea_id = user_id_of(admin, "lea")
    assert admin.patch(f"/api/users/{lea_id}", json={"disabled": True}).status_code == 200
    assert admin.put(f"/api/admin/accounts/{lea_id}/look", json=WARM).json() == WARM
