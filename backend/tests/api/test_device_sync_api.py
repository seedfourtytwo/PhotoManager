"""Keep on my phone (FEATURES 10.6) through the real app: rules from a signed-in browser, the
manifest and the originals through the device's own token (docs/contracts/api-v1.md, "Keep on
my phone").

Library: the admin's source "family" (everyone: download) holds beach, garden, snow and shot;
"view only" (everyone: view) holds look. Lea is a member; her phone has a device token.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from tests.api.conftest import BASE, add_user, asset_id_of, import_folder, refusal, services_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

PHOTOS = {
    "beach": datetime(2019, 7, 4, 12),
    "garden": datetime(2019, 8, 1, 9),
    "snow": datetime(2021, 1, 2, 10),
    "shot": datetime(2021, 3, 5, 8),
}


@dataclass
class World:
    admin: TestClient
    lea: TestClient
    phone: TestClient  # no cookies: only the device token
    device_id: int
    ids: dict[str, int]
    album_id: int


@pytest.fixture
def world(admin: TestClient, tmp_path: Path) -> World:
    family, viewing = tmp_path / "family", tmp_path / "view"
    for seed, (name, taken) in enumerate(PHOTOS.items()):
        write_photo(family / f"{name}.jpg", seed=seed, taken=taken)
    write_photo(viewing / "look.jpg", seed=9, taken=datetime(2020, 5, 5, 5))
    family_id = import_folder(admin, family, "family")
    view_id = import_folder(admin, viewing, "view only")
    assert admin.put(
        f"/api/sources/{family_id}/access", json={"everyone": "download", "users": []}
    ).is_success
    assert admin.put(
        f"/api/sources/{view_id}/access", json={"everyone": "view", "users": []}
    ).is_success
    ids = {name: asset_id_of(admin, family_id, f"{name}.jpg") for name in PHOTOS}
    ids["look"] = asset_id_of(admin, view_id, "look.jpg")
    lea = add_user(admin, "lea")
    album = lea.post("/api/albums", json={"title": "Summer"}).json()
    items = [ids["beach"], ids["garden"], ids["look"]]
    assert lea.post(f"/api/albums/{album['id']}/items", json={"asset_ids": items}).is_success
    created = lea.post("/api/devices", json={"name": "Lea's iPhone", "platform": "ios"}).json()
    phone = TestClient(admin.app, base_url=BASE)
    phone.headers["Authorization"] = f"Bearer {created['token']}"
    return World(admin, lea, phone, created["device"]["id"], ids, album["id"])


def _keep(world: World, mode: str = "include", **what: object) -> dict:  # type: ignore[type-arg]
    response = world.lea.post(
        f"/api/devices/{world.device_id}/sync/rules", json={"mode": mode, **what}
    )
    assert response.status_code == 200, response.text
    rule: dict = response.json()  # type: ignore[type-arg]
    return rule


def _manifest(world: World, **params: str | int) -> dict:  # type: ignore[type-arg]
    response = world.phone.get("/api/sync/manifest", params=params)
    assert response.status_code == 200, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


def _ids(body: dict) -> list[int]:  # type: ignore[type-arg]
    return [item["id"] for item in body["items"]]


# --- the device: manifest and originals --------------------------------------------------------


def test_the_phone_gets_the_album_but_not_what_its_owner_may_only_view(world: World) -> None:
    """An album grants view only (ARCHITECTURE §7); keeping is a download, so "look" stays
    on the server."""
    _keep(world, kind="album", album_id=world.album_id)

    body = _manifest(world)

    assert _ids(body) == sorted([world.ids["beach"], world.ids["garden"]])
    first = body["items"][0]
    assert set(first) == {"id", "hash", "name", "taken_at", "bytes", "mime_type", "url"}
    assert first["name"].endswith(".jpg")
    assert first["url"] == f"/api/sync/assets/{first['id']}/original"
    assert (body["total"], body["remaining"], body["next_after"]) == (2, 2, None)
    assert body["total_bytes"] == sum(i["bytes"] for i in body["items"])


def _saved(world: World, *names: str) -> dict:  # type: ignore[type-arg]
    response = world.phone.post("/api/sync/sent", json={"ids": [world.ids[n] for n in names]})
    assert response.status_code == 200, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


def test_an_original_comes_whole_and_is_new_until_the_phone_says_it_saved_it(
    world: World,
) -> None:
    _keep(world, kind="album", album_id=world.album_id)
    beach = world.ids["beach"]
    library_file = services_of(world.admin).repo.get_asset(beach)
    assert library_file is not None

    got = world.phone.get(f"/api/sync/assets/{beach}/original")

    assert got.status_code == 200
    stored = services_of(world.admin).store.absolute(library_file.library_path)
    assert got.content == stored.read_bytes(), "the untouched original"
    assert "attachment" in got.headers["content-disposition"]
    assert len(_manifest(world, new="true")["items"]) == 2, "downloaded is not saved"
    assert _saved(world, "beach") == {"sent": 1}
    assert _ids(_manifest(world, new="true")) == [world.ids["garden"]]
    assert _manifest(world, new="true")["remaining"] == 1
    assert _ids(_manifest(world)) == sorted([beach, world.ids["garden"]]), "still on the list"


def test_send_everything_again(world: World) -> None:
    _keep(world, kind="album", album_id=world.album_id)
    _saved(world, "beach", "garden")
    _saved(world, "beach")  # said twice: harmless
    assert _manifest(world, new="true")["items"] == []
    answer = world.lea.post(f"/api/devices/{world.device_id}/sync/resend")
    assert answer.json() == {"forgotten": 2}
    assert len(_manifest(world, new="true")["items"]) == 2


def test_only_photos_on_the_list_can_be_said_saved(world: World) -> None:
    _keep(world, kind="album", album_id=world.album_id)
    for off_list in ("snow", "look"):  # Lea may see both; neither is on the list
        ids = [world.ids["beach"], world.ids[off_list]]
        answer = world.phone.post("/api/sync/sent", json={"ids": ids})
        assert answer.status_code == 422
    assert len(_manifest(world, new="true")["items"]) == 2, "nothing was marked"
    assert world.lea.post("/api/sync/sent", json={"ids": [world.ids["beach"]]}).status_code == 401
    too_many = world.phone.post("/api/sync/sent", json={"ids": list(range(1, 202))})
    assert too_many.status_code == 422


def test_a_photo_off_the_list_is_not_served_to_the_device(world: World) -> None:
    _keep(world, kind="album", album_id=world.album_id)
    snow = world.phone.get(f"/api/sync/assets/{world.ids['snow']}/original")
    assert refusal(snow) == (404, {"detail": "photo not found"}), "Lea may see it; not on the list"


def test_pages_are_small_and_follow_one_another(world: World) -> None:
    _keep(world, kind="filter", filters={})  # everything Lea may download
    first = _manifest(world, limit=2)
    assert len(first["items"]) == 2 and first["next_after"] == first["items"][-1]["id"]
    rest = _manifest(world, limit=2, after=first["next_after"])
    assert len(rest["items"]) == 2 and rest["next_after"] is None
    too_many = world.phone.get("/api/sync/manifest", params={"limit": 201})
    assert too_many.status_code == 422


def test_excludes_win_over_includes(world: World) -> None:
    services = services_of(world.admin)
    services.ml.store.replace_model_tags(
        world.ids["shot"], "m", [TagScore("screenshot", 0.3)], screen_or_document=True
    )
    face = Face(BoundingBox(0.1, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))
    store = services.ml.store
    person = store.create_person(store.replace_faces(world.ids["garden"], "f", [face])[0])
    store.assign_face(store.replace_faces(world.ids["snow"], "f", [face])[0], person)

    _keep(world, kind="filter", filters={"year": 2021})  # snow, shot
    _keep(world, kind="album", album_id=world.album_id)  # beach, garden
    _keep(world, "exclude", kind="person", person_id=person)  # garden, snow
    _keep(world, "exclude", kind="filter", filters={"q": "tag:screenshot"})  # shot

    assert _ids(_manifest(world)) == [world.ids["beach"]]


def test_hidden_and_trashed_photos_never_go(world: World) -> None:
    _keep(world, kind="album", album_id=world.album_id)
    beach, garden = world.ids["beach"], world.ids["garden"]
    assert world.lea.patch(f"/api/assets/{beach}/state", json={"hidden": True}).is_success
    assert world.admin.request("DELETE", "/api/assets", json={"ids": [garden]}).is_success
    assert _ids(_manifest(world)) == []


def test_only_the_device_token_reads_the_manifest(world: World) -> None:
    assert world.lea.get("/api/sync/manifest").status_code == 401, "a browser has no list"
    world.phone.headers["Authorization"] = "Bearer pa_dev_made_up"
    assert world.phone.get("/api/sync/manifest").status_code == 401
    assert world.phone.get(f"/api/sync/assets/{world.ids['beach']}/original").status_code == 401


def test_a_revoked_phone_gets_nothing(world: World) -> None:
    _keep(world, kind="album", album_id=world.album_id)
    assert world.lea.delete(f"/api/devices/{world.device_id}").status_code == 204
    assert world.phone.get("/api/sync/manifest").status_code == 401
    assert world.phone.get(f"/api/sync/assets/{world.ids['beach']}/original").status_code == 401


def test_the_device_token_cannot_change_its_own_rules(world: World) -> None:
    sync = f"/api/devices/{world.device_id}/sync"
    assert world.phone.get(sync).status_code == 401
    keep = {"kind": "filter", "filters": {}, "mode": "include"}
    assert world.phone.post(f"{sync}/rules", json=keep).status_code == 401


# --- the browser: rules and the summary --------------------------------------------------------


def test_the_summary_lists_rules_counts_size_and_last_sync(world: World) -> None:
    kept = _keep(world, kind="album", album_id=world.album_id)
    _keep(world, "exclude", kind="filter", filters={"q": "tag:screenshot"})
    _saved(world, "beach")
    _manifest(world)

    body = world.lea.get(f"/api/devices/{world.device_id}/sync").json()

    assert body["device"]["id"] == world.device_id and body["device"]["last_sync_at"]
    assert [(r["kind"], r["mode"], r["label"], r["count"]) for r in body["rules"]] == [
        ("album", "include", "Summer", 3),
        ("filter", "exclude", None, 0),
    ]
    assert body["rules"][0] == kept | {"count": 3}
    assert body["rules"][0]["view_only"] == 1, "look: Lea may only view it"
    assert body["rules"][1]["filters"] == {"q": "tag:screenshot"}
    assert (body["count"], body["sent"]) == (2, 1)
    assert body["bytes"] > 0


def test_keeping_the_same_thing_again_changes_its_mode(world: World) -> None:
    first = _keep(world, kind="album", album_id=world.album_id)
    again = _keep(world, "exclude", kind="album", album_id=world.album_id)
    assert again["id"] == first["id"] and again["mode"] == "exclude"
    same = _keep(world, kind="filter", filters={"year": 2021, "favourite": True})
    reordered = _keep(world, "exclude", kind="filter", filters={"favourite": True, "year": 2021})
    assert reordered["id"] == same["id"], "the same filters, whatever their order"


def test_a_rule_is_removed(world: World) -> None:
    rule = _keep(world, kind="album", album_id=world.album_id)
    path = f"/api/devices/{world.device_id}/sync/rules/{rule['id']}"
    assert world.lea.delete(path).status_code == 204
    assert world.lea.delete(path).status_code == 404
    assert world.lea.get(f"/api/devices/{world.device_id}/sync").json()["rules"] == []


def test_rules_that_make_no_sense_are_refused(world: World) -> None:
    rules = f"/api/devices/{world.device_id}/sync/rules"
    no_album = {"kind": "album", "mode": "include"}
    assert world.lea.post(rules, json=no_album).status_code == 422
    unknown = {"kind": "filter", "filters": {"colour": "red"}, "mode": "include"}
    assert world.lea.post(rules, json=unknown).status_code == 422
    bad_month = {"kind": "filter", "filters": {"month": 3}, "mode": "include"}
    assert refusal(world.lea.post(rules, json=bad_month)) == (
        400,
        {"detail": "a month needs a year"},
    )
    not_hers = {"kind": "album", "album_id": 999, "mode": "include"}
    assert world.lea.post(rules, json=not_hers).status_code == 404


def test_someone_elses_device_is_not_found(world: World) -> None:
    tom = add_user(world.admin, "tom")
    assert tom.get(f"/api/devices/{world.device_id}/sync").status_code == 404
    keep = {"kind": "filter", "filters": {}, "mode": "include"}
    assert tom.post(f"/api/devices/{world.device_id}/sync/rules", json=keep).status_code == 404


def test_an_album_she_cannot_see_cannot_be_kept(world: World) -> None:
    admin_album = world.admin.post("/api/albums", json={"title": "Mine"}).json()
    keep = {"kind": "album", "album_id": admin_album["id"], "mode": "include"}
    answer = world.lea.post(f"/api/devices/{world.device_id}/sync/rules", json=keep)
    assert answer.status_code == 404
