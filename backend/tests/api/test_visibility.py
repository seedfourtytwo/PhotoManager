"""Who sees what, at which level — through the API (FEATURES 8.2 to 8.4, ARCHITECTURE §7).

One world, many users. Every expectation is a row in ``EXPECTED``; each row is checked on
the timeline, the detail endpoint, facets, calendar, image endpoints and downloads.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, asset_id_of, import_folder, user_id_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

PHOTOS = ["p1", "p_priv", "p2", "p3", "p4", "p5", "p6", "p7"]

# user → photo → level (None = must not even know it exists)
EXPECTED: dict[str, dict[str, str | None]] = {
    "admin": {
        "p1": "edit",
        "p_priv": "edit",
        "p2": "edit",
        "p3": "edit",
        "p4": "edit",
        "p5": None,
        "p6": "edit",
        "p7": "edit",
    },
    "lea": {
        "p1": "download",
        "p_priv": None,
        "p2": "download",
        "p3": None,
        "p4": "download",
        "p5": "edit",
        "p6": "edit",
        "p7": "download",
    },
    "tom": {
        "p1": "download",
        "p_priv": None,
        "p2": "view",
        "p3": None,
        "p4": "download",
        "p5": None,
        "p6": "view",
        "p7": None,
    },
    "gus": {
        "p1": "download",
        "p_priv": None,
        "p2": None,
        "p3": None,
        "p4": "download",
        "p5": None,
        "p6": "view",
        "p7": "download",
    },
}


@dataclass
class World:
    clients: dict[str, TestClient]
    ids: dict[str, int]


@pytest.fixture
def world(admin: TestClient, tmp_path: Path) -> World:
    """Sources:
    S1 family      everyone: download                 p1, p_priv (private, owner admin), p4
    S2 lea-view    only lea: view                     p2, p7
    S3 restricted  nobody but its owner (admin)       p3, p4 (same file as in S1)
    S4 lea's own   owner lea, everyone: view          p5 (private, by lea), p6
    Albums (by lea): "Trip" = [p2, p5] shared with tom (viewer);
                     "For Gus" = [p7] shared with gus (editor).
    """
    folders = {name: tmp_path / name for name in ("s1", "s2", "s3", "s4")}
    placement = {
        "p1": ["s1"],
        "p_priv": ["s1"],
        "p2": ["s2"],
        "p7": ["s2"],
        "p3": ["s3"],
        "p4": ["s1", "s3"],
        "p5": ["s4"],
        "p6": ["s4"],
    }
    for seed, (photo, where) in enumerate(placement.items()):
        for folder in where:
            write_photo(folders[folder] / f"{photo}.jpg", seed=seed)
    clients = {
        "admin": admin,
        "lea": add_user(admin, "lea"),
        "tom": add_user(admin, "tom"),
        "gus": add_user(admin, "gus", "guest"),
    }
    lea_id, tom_id, gus_id = (user_id_of(admin, n) for n in ("lea", "tom", "gus"))
    s1 = import_folder(admin, folders["s1"], "family")
    s2 = import_folder(admin, folders["s2"], "lea-view")
    s3 = import_folder(admin, folders["s3"], "restricted")
    s4 = import_folder(admin, folders["s4"], "lea's own")
    put = admin.put
    assert put(
        f"/api/sources/{s2}/access",
        json={"everyone": None, "users": [{"user_id": lea_id, "level": "view"}]},
    ).is_success
    assert put(f"/api/sources/{s3}/access", json={"everyone": None, "users": []}).is_success
    assert put(f"/api/sources/{s4}/access", json={"everyone": "view", "users": []}).is_success
    assert admin.patch(f"/api/sources/{s4}", json={"owner_id": lea_id}).is_success
    ids = {p: asset_id_of(admin, s1, f"{p}.jpg") for p in ("p1", "p_priv", "p4")}
    ids |= {p: asset_id_of(admin, s2, f"{p}.jpg") for p in ("p2", "p7")}
    ids |= {"p3": asset_id_of(admin, s3, "p3.jpg")}
    ids |= {p: asset_id_of(admin, s4, f"{p}.jpg") for p in ("p5", "p6")}
    assert admin.patch(f"/api/assets/{ids['p_priv']}/state", json={"private": True}).is_success
    lea = clients["lea"]
    assert lea.patch(f"/api/assets/{ids['p5']}/state", json={"private": True}).is_success
    trip = lea.post("/api/albums", json={"title": "Trip", "asset_ids": [ids["p2"], ids["p5"]]})
    assert trip.status_code == 201, trip.text
    assert lea.put(
        f"/api/albums/{trip.json()['id']}/members", json=[{"user_id": tom_id, "role": "viewer"}]
    ).is_success
    gus_album = lea.post("/api/albums", json={"title": "For Gus", "asset_ids": [ids["p7"]]})
    assert lea.put(
        f"/api/albums/{gus_album.json()['id']}/members",
        json=[{"user_id": gus_id, "role": "editor"}],
    ).is_success
    return World(clients, ids)


def visible_ids(client: TestClient) -> set[int]:
    return {a["id"] for a in client.get("/api/assets", params={"limit": 500}).json()["items"]}


@pytest.mark.parametrize("user", list(EXPECTED))
def test_each_user_sees_exactly_their_photos_at_their_level(world: World, user: str) -> None:
    client = world.clients[user]
    expected = EXPECTED[user]
    should_see = {world.ids[p] for p, level in expected.items() if level}
    assert visible_ids(client) == should_see
    facets = client.get("/api/assets/facets").json()
    assert facets["total"] == len(should_see)
    assert sum(d["count"] for d in client.get("/api/calendar").json()) == len(should_see)
    for photo, level in expected.items():
        asset_id = world.ids[photo]
        detail = client.get(f"/api/assets/{asset_id}")
        thumb = client.get(f"/api/assets/{asset_id}/thumb")
        original = client.get(f"/api/assets/{asset_id}/original")
        if level is None:
            assert detail.status_code == 404, f"{user} must not see {photo}"
            assert thumb.status_code == 404 and original.status_code == 404
            continue
        assert detail.json()["level"] == level, f"{user} on {photo}"
        assert thumb.status_code == 200
        assert original.status_code == (200 if level in ("download", "edit") else 403)


@pytest.mark.parametrize("user", list(EXPECTED))
def test_zip_downloads_leave_out_what_you_may_not_download(world: World, user: str) -> None:
    client = world.clients[user]
    body = {"ids": list(world.ids.values()), "format": "original"}
    response = client.post("/api/downloads", json=body)
    allowed = [p for p, lvl in EXPECTED[user].items() if lvl in ("download", "edit")]
    assert response.status_code == 200
    assert int(response.headers["x-skipped"]) == len(PHOTOS) - len(allowed)


def test_album_titles_and_sources_do_not_leak(world: World) -> None:
    tom = world.clients["tom"]
    trip = tom.get("/api/albums").json()
    assert [a["title"] for a in trip] == ["Trip"] and trip[0]["role"] == "viewer"
    items = tom.get(f"/api/albums/{trip[0]['id']}").json()["items"]
    assert [i["id"] for i in items] == [world.ids["p2"]], "private p5 stays hidden in albums"
    assert trip[0]["count"] == 1
    detail = tom.get(f"/api/assets/{world.ids['p2']}").json()
    assert detail["origins"] == [], "tom can't see the source p2 came from"
    labels = {s["label"] for s in tom.get("/api/assets/facets").json()["sources"]}
    assert labels == {"family", "lea's own"}
    assert {s["label"] for s in tom.get("/api/sources").json()} == {"family", "lea's own"}


def test_only_the_owner_or_an_admin_may_mark_private(world: World) -> None:
    tom = world.clients["tom"]
    r = tom.patch(f"/api/assets/{world.ids['p1']}/state", json={"private": True})
    assert r.status_code == 403
    lea = world.clients["lea"]
    assert lea.patch(f"/api/assets/{world.ids['p6']}/state", json={"private": True}).is_success
    assert world.ids["p6"] not in visible_ids(tom)
    assert world.ids["p6"] not in visible_ids(world.clients["admin"]), "not even admins"


def test_source_access_can_be_read_and_changed_only_by_admins(world: World) -> None:
    admin, tom = world.clients["admin"], world.clients["tom"]
    sources = {s["label"]: s for s in admin.get("/api/sources").json()}
    family = sources["family"]
    assert family["owner_id"] == 1 and family["asset_count"] == 3
    assert admin.get(f"/api/sources/{family['id']}/access").json() == {
        "everyone": "download",
        "users": [],
    }
    assert tom.get(f"/api/sources/{family['id']}/access").status_code == 200
    restricted = sources["restricted"]["id"]
    assert tom.get(f"/api/sources/{restricted}/access").status_code == 404
    denied = tom.put(f"/api/sources/{family['id']}/access", json={"everyone": None, "users": []})
    assert denied.status_code == 403
    bad = admin.put(
        f"/api/sources/{family['id']}/access",
        json={"everyone": None, "users": [{"user_id": 999, "level": "view"}]},
    )
    assert bad.status_code == 422
    admin.put(f"/api/sources/{family['id']}/access", json={"everyone": None, "users": []})
    assert world.ids["p1"] not in visible_ids(tom)


# --- local ML: search, similar photos and people start from the same rule --------------------


def _fake_ml_index(world: World) -> None:
    """Index every photo with a fake CLIP model and give each a face of one person."""
    from photo_assistant.app.search import SemanticSearch, SimilarPhotos
    from photo_assistant.domain.faces import BoundingBox, Face
    from tests.api.conftest import services_of
    from tests.ml.fakes import FakeClip

    ml = services_of(world.clients["admin"]).ml
    clip = FakeClip(dim=3)
    face_ids = []
    for i, asset_id in enumerate(world.ids.values()):
        ml.store.save_clip(asset_id, clip.name, (1.0, i / 10, 0.0))
        face = Face(BoundingBox(0.1, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))
        face_ids += ml.store.replace_faces(asset_id, "f", [face])
    person = ml.store.create_person(face_ids[0])
    for face_id in face_ids[1:]:
        ml.store.assign_face(face_id, person)
    ml.store.rename_person(person, "Lea")
    ml.clip = clip  # type: ignore[assignment]
    ml.search = SemanticSearch(clip, ml.store)
    ml.similar = SimilarPhotos(ml.store, clip.name)


@pytest.mark.parametrize("user", list(EXPECTED))
def test_search_similar_and_people_never_show_hidden_photos(world: World, user: str) -> None:
    _fake_ml_index(world)
    client = world.clients[user]
    should_see = {world.ids[p] for p, level in EXPECTED[user].items() if level}

    for q in ("sunset", "person:Lea", "sunset person:Lea"):
        found = client.get("/api/search", params={"q": q, "limit": 200}).json()["items"]
        assert {a["id"] for a in found} == should_see, q
    (lea,) = client.get("/api/people").json()
    assert lea["face_count"] == len(should_see)
    assert lea["cover"]["asset_id"] in should_see
    people_assets = client.get(f"/api/people/{lea['id']}/assets").json()["items"]
    assert {a["id"] for a in people_assets} == should_see
    for photo, level in EXPECTED[user].items():
        similar = client.get(f"/api/assets/{world.ids[photo]}/similar")
        faces = client.get(f"/api/assets/{world.ids[photo]}/faces")
        if level is None:
            assert similar.status_code == 404 and faces.status_code == 404, photo
        else:
            assert {a["id"] for a in similar.json()} == should_see - {world.ids[photo]}
            assert len(faces.json()) == 1


def test_the_visible_id_set_is_the_timeline(world: World) -> None:
    from photo_assistant.domain.access import Viewer
    from photo_assistant.domain.library_filter import AssetFilter
    from tests.api.conftest import services_of

    services = services_of(world.clients["admin"])
    for name, client in world.clients.items():
        me = client.get("/api/auth/me").json()
        user = services.repo.get_user(me["id"])
        assert user is not None
        ids = services.repo.visible_asset_ids(Viewer.of(user))
        timeline = [
            a["id"] for a in client.get("/api/assets", params={"limit": 500}).json()["items"]
        ]
        assert ids == timeline, name
        assert services.repo.visible_asset_ids(Viewer.of(user), AssetFilter(year=1900)) == []
