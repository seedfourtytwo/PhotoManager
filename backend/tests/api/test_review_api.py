"""The "To review" list over HTTP, with real imports: a look-alike from a later import waits
for a decision; keep and discard; who may decide."""

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, asset_id_of, import_folder, services_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


@pytest.fixture
def ids(admin: TestClient, tmp_path: Path) -> dict[str, int]:
    """One photo in the library, then an import with the same picture saved again and a new one."""
    write_photo(tmp_path / "a" / "orig.jpg", seed=1, taken=datetime(2019, 7, 4, 18, 30))
    first = import_folder(admin, tmp_path / "a", "first")
    write_photo(tmp_path / "b" / "copy.jpg", seed=1, taken=datetime(2023, 2, 2, 8, 0))
    write_photo(tmp_path / "b" / "new.jpg", seed=50, taken=datetime(2023, 2, 3, 8, 0))
    second = import_folder(admin, tmp_path / "b", "second")
    return {
        "orig": asset_id_of(admin, first, "orig.jpg"),
        "copy": asset_id_of(admin, second, "copy.jpg"),
        "new": asset_id_of(admin, second, "new.jpg"),
    }


def timeline(client: TestClient) -> set[int]:
    return {a["id"] for a in client.get("/api/assets").json()["items"]}


def test_a_look_alike_waits_beside_the_photo_it_resembles(
    admin: TestClient, ids: dict[str, int]
) -> None:
    assert timeline(admin) == {ids["orig"], ids["new"]}
    assert admin.get("/api/review/count").json() == {"count": 1}
    body = admin.get("/api/review").json()
    assert body["count"] == 1 and [g["reason"] for g in body["groups"]] == ["lookalike"]
    (item,) = body["groups"][0]["items"]
    assert (item["asset"]["id"], item["like"]["id"]) == (ids["copy"], ids["orig"])
    assert admin.get(f"/api/assets/{ids['copy']}/thumb").status_code == 200, "it can be looked at"
    assert admin.get(f"/api/assets/{ids['copy']}").status_code == 404, "but is not in the library"


def test_keep_puts_it_in_the_library_for_good(admin: TestClient, ids: dict[str, int]) -> None:
    assert admin.post("/api/review/keep", json={"ids": [ids["copy"]]}).json() == {"kept": 1}
    assert timeline(admin) == set(ids.values())
    assert admin.get("/api/review").json() == {"count": 0, "groups": []}
    services_of(admin).worker.run_until_idle()  # regrouping must not hold it again
    assert timeline(admin) == set(ids.values())


def test_discard_moves_it_to_the_trash(admin: TestClient, ids: dict[str, int]) -> None:
    response = admin.post("/api/review/discard", json={"ids": [ids["copy"]]})
    assert response.json() == {"discarded": 1}
    assert admin.get("/api/review").json()["count"] == 0
    assert [t["id"] for t in admin.get("/api/trash").json()] == [ids["copy"]]
    assert timeline(admin) == {ids["orig"], ids["new"]}


def test_clutter_is_listed_under_its_own_reason_after_look_alikes(
    admin: TestClient, ids: dict[str, int]
) -> None:
    from photo_assistant.domain.tags import TagScore

    services_of(admin).review.hold_clutter(ids["new"], [TagScore("receipt", 0.2)])
    body = admin.get("/api/review").json()
    assert [(g["reason"], len(g["items"])) for g in body["groups"]] == [
        ("lookalike", 1),
        ("receipt", 1),
    ]
    assert body["groups"][1]["items"][0]["like"] is None


def test_only_photos_waiting_for_review_can_be_decided(
    admin: TestClient, ids: dict[str, int]
) -> None:
    for action in ("keep", "discard"):
        assert admin.post(f"/api/review/{action}", json={"ids": [ids["orig"]]}).status_code == 404
        assert admin.post(f"/api/review/{action}", json={"ids": [9999]}).status_code == 404
    assert timeline(admin) == {ids["orig"], ids["new"]}


def test_deciding_needs_edit_rights_and_a_session(admin: TestClient, ids: dict[str, int]) -> None:
    lea = add_user(admin, "lea")  # new sources are open to everyone at "download": no edit
    assert lea.get("/api/review").json()["count"] == 1
    for action in ("keep", "discard"):
        assert lea.post(f"/api/review/{action}", json={"ids": [ids["copy"]]}).status_code == 403
    assert admin.get("/api/review/count").json() == {"count": 1}
    lea.post("/api/auth/logout")
    assert lea.get("/api/review").status_code == 401
