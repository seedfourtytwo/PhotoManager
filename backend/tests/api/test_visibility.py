"""Who sees what, at which level — through the API (FEATURES 8.2 to 8.4, ARCHITECTURE §7).

One world, many users. Every expectation is a row in ``EXPECTED``; each row is checked on
the timeline, the detail endpoint, facets, calendar, image endpoints and downloads.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, asset_id_of, import_folder, services_of, user_id_of
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
        "p2": "view",  # her own album "Trip" grants view only (owner decision, QA A1)
        "p3": None,
        "p4": "download",
        "p5": "edit",
        "p6": "edit",
        "p7": "view",  # S2 grants view; owning the album adds nothing
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
        "p7": "view",  # album editor: albums grant view, never download
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


def test_albums_grant_view_only_so_an_album_never_unlocks_a_download(world: World) -> None:
    """QA A1: lea could only *view* p2, put it in her own album and then download it."""
    lea, gus = world.clients["lea"], world.clients["gus"]
    for client, photo in ((lea, "p2"), (lea, "p7"), (gus, "p7")):
        asset_id = world.ids[photo]
        assert client.get(f"/api/assets/{asset_id}").json()["level"] == "view"
        assert client.get(f"/api/assets/{asset_id}/original").status_code == 403
        assert client.get(f"/api/assets/{asset_id}/download").status_code == 403
        body = {"ids": [asset_id], "format": "original"}
        assert client.post("/api/downloads", json=body).headers["x-skipped"] == "1"


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
    restricted = sources["restricted"]["id"]
    for source_id in (family["id"], restricted):  # admin-only (QA A12)
        assert tom.get(f"/api/sources/{source_id}/access").status_code == 403
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


@pytest.mark.parametrize("user", list(EXPECTED))
def test_people_and_similar_answer_from_the_viewer_as_from_the_list_of_their_photos(
    world: World, user: str
) -> None:
    """The routes hand the ML store the viewer, not every id they may see. The answers are
    what the routes built from that list (the oracle below), also with a photo the viewer
    has hidden, and the list is no longer copied into the candidate table."""
    from photo_assistant.api.routes.ml import PersonOut
    from photo_assistant.domain.access import Viewer

    _fake_ml_index(world)
    services, client = services_of(world.clients["admin"]), world.clients[user]
    ml = services.ml
    (first_face,) = ml.store.faces_of_asset(world.ids["p3"])  # p3: only the admin sees it
    tom = ml.store.create_empty_person("Tom")
    ml.store.move_faces([first_face.id], tom)
    assert client.patch(f"/api/assets/{world.ids['p1']}/state", json={"hidden": True}).is_success
    account = services.repo.get_user(client.get("/api/auth/me").json()["id"])
    assert account is not None
    ids = services.repo.visible_asset_ids(Viewer.of(account))
    assert world.ids["p1"] not in ids and ids

    statements: list[str] = []
    ml.store._conn.set_trace_callback(statements.append)
    try:
        people = client.get("/api/people").json()
        pages: dict[int, list[int]] = {}
        for person in people:
            assert client.get(f"/api/people/{person['id']}").json() == person
            cursor, pages[person["id"]] = None, []
            while True:
                params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
                page = client.get(f"/api/people/{person['id']}/assets", params=params).json()
                pages[person["id"]] += [a["id"] for a in page["items"]]
                cursor = page["next_cursor"]
                if cursor is None:
                    break
        similar = {
            i: [(a["id"], a["score"]) for a in client.get(f"/api/assets/{i}/similar").json()]
            for i in ids
        }
    finally:
        ml.store._conn.set_trace_callback(None)
    assert [s for s in statements if "ml_candidates" in s] == []

    expected = [PersonOut.of(p).model_dump() for p in ml.people.list_all(ids)]
    assert people == expected and people
    assert (tom in pages) == (world.ids["p3"] in ids)
    for person_id, page_ids in pages.items():
        theirs = set(ml.people.assets(person_id, ids))
        assert page_ids == [i for i in ids if i in theirs]  # timeline order, as before
    for asset_id in ids:
        hits = ml.similar(asset_id, ids, 50)
        assert similar[asset_id] == [(h.asset_id, pytest.approx(h.score)) for h in hits]


@pytest.mark.parametrize("user", ["admin", "lea", "tom"])
def test_people_changes_reach_only_people_and_faces_on_photos_you_see(
    world: World, user: str
) -> None:
    _fake_ml_index(world)
    client = world.clients[user]
    store = services_of(world.clients["admin"]).ml.store
    (hidden_face,) = store.faces_of_asset(world.ids["p3"])  # p3: only the admin sees it
    tom = store.create_empty_person("Tom")
    store.move_faces([hidden_face.id], tom)
    (lea,) = (p["id"] for p in client.get("/api/people").json() if p["name"] == "Lea")
    sees_tom = EXPECTED[user]["p3"] is not None
    there = 200 if sees_tom else 404

    assert client.get(f"/api/people/{tom}").status_code == there
    assert client.get(f"/api/people/{tom}/assets").status_code == there
    assert client.patch(f"/api/people/{tom}", json={"name": "Tomas"}).status_code == there
    split = client.post("/api/people/split", json={"face_ids": [hidden_face.id], "name": "X"})
    assert split.status_code == there
    if sees_tom:
        moved_to = split.json()["id"]
        merged = client.post(f"/api/people/{lea}/merge", json={"source_ids": [moved_to]})
        assert merged.status_code == 200
    else:
        assert (hidden := store.get_face(hidden_face.id)) is not None
        assert hidden.person_id == tom, "untouched"
        assert (
            client.post(f"/api/people/{lea}/merge", json={"source_ids": [tom]}).status_code == 404
        )
        (own_face,) = store.faces_of_asset(world.ids["p1"])
        moved = client.post("/api/people/split", json={"face_ids": [own_face.id], "name": "Me"})
        assert moved.status_code == 200 and moved.json()["face_count"] == 1
    renamed = client.patch(f"/api/people/{lea}", json={"name": "Léa"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Léa"


@pytest.mark.parametrize("user", list(EXPECTED))
def test_a_portrait_is_only_ever_cut_from_a_photo_you_see(world: World, user: str) -> None:
    _fake_ml_index(world)
    client = world.clients[user]
    store = services_of(world.clients["admin"]).ml.store
    should_see = {world.ids[p] for p, level in EXPECTED[user].items() if level}
    (lea,) = client.get("/api/people").json()
    (hidden_face,) = store.faces_of_asset(world.ids["p3"])  # p3: only the admin sees it
    (shared_face,) = store.faces_of_asset(world.ids["p1"])  # p1: everyone sees it
    person = f"/api/people/{lea['id']}"
    sees_p3 = EXPECTED[user]["p3"] is not None
    there = 200 if sees_p3 else 404
    may_edit = user != "gus"

    faces = client.get(f"{person}/faces", params={"limit": 100}).json()
    assert {f["asset_id"] for f in faces} == should_see
    assert client.get(f"/api/faces/{hidden_face.id}/portrait").status_code == there
    assert client.get(f"/api/faces/{shared_face.id}/portrait").status_code == 200

    circle = {"cx": 0.5, "cy": 0.5, "size": 0.5}
    hidden = client.put(f"{person}/portrait", json={"face_id": hidden_face.id} | circle)
    assert hidden.status_code == (there if may_edit else 403)
    admin = world.clients["admin"]
    assert admin.put(f"{person}/portrait", json={"face_id": hidden_face.id} | circle).is_success
    mine = client.get(person).json()["portrait"]
    assert mine["asset_id"] in should_see
    assert mine["chosen"] is sees_p3, "the cut chosen on a photo you do not see is not yours"
    assert (mine["face_id"] == hidden_face.id) is sees_p3
    assert client.get(mine["url"]).status_code == 200

    shared = client.put(f"{person}/portrait", json={"face_id": shared_face.id} | circle)
    assert shared.status_code == (200 if may_edit else 403)
    if may_edit:
        assert client.get(person).json()["portrait"]["chosen"] is True
        assert admin.get(person).json()["portrait"]["face_id"] == shared_face.id, "one for all"


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


# --- QA A3: "first importer owns the photo" ----------------------------------------------------


def _source_id(admin: TestClient, label: str) -> int:
    found: int = next(s["id"] for s in admin.get("/api/sources").json() if s["label"] == label)
    return found


def test_private_hides_only_from_viewers_who_reach_it_solely_through_the_markers_sources(
    world: World, tmp_path: Path
) -> None:
    """Lea's source had the photo first, so she 'owned' it and could hide it from the admin
    whose own family source holds the same file. Now private only hides it from people who
    reach it through lea's own sources."""
    admin, lea, tom = (world.clients[n] for n in ("admin", "lea", "tom"))
    s4 = _source_id(admin, "lea's own")
    write_photo(tmp_path / "s4" / "shared.jpg", seed=50)
    assert admin.post(f"/api/sources/{s4}/scan").status_code == 202
    services_of(admin).worker.run_until_idle()
    write_photo(tmp_path / "s5" / "shared.jpg", seed=50)
    s5 = import_folder(admin, tmp_path / "s5", "family two")
    shared = asset_id_of(admin, s4, "shared.jpg")
    assert asset_id_of(admin, s5, "shared.jpg") == shared, "one photo, two sources"

    assert lea.patch(f"/api/assets/{shared}/state", json={"private": True}).is_success
    assert lea.get(f"/api/assets/{shared}").json()["private"] is True
    assert admin.get(f"/api/assets/{shared}").json()["level"] == "edit", "admin's own source"
    assert tom.get(f"/api/assets/{shared}").json()["level"] == "download", "via family two"

    assert admin.put(f"/api/sources/{s5}/access", json={"everyone": None, "users": []}).is_success
    assert tom.get(f"/api/assets/{shared}").status_code == 404, "only lea's source is left"
    assert shared in visible_ids(admin)


def test_marking_private_needs_edit_from_a_source(world: World) -> None:
    lea = world.clients["lea"]
    denied = lea.patch(f"/api/assets/{world.ids['p2']}/state", json={"private": True})
    assert denied.status_code == 403, "lea only views p2"


def test_an_admin_cannot_see_list_or_purge_a_members_private_photo_in_the_trash(
    world: World,
) -> None:
    admin, lea = world.clients["admin"], world.clients["lea"]
    p5 = world.ids["p5"]  # private by lea, only in lea's own source
    assert lea.request("DELETE", "/api/assets", json={"ids": [p5]}).json() == {"trashed": 1}
    assert p5 in {t["id"] for t in lea.get("/api/trash").json()}
    assert p5 not in {t["id"] for t in admin.get("/api/trash").json()}
    assert admin.post("/api/trash/empty", json={"ids": [p5]}).json() == {"purged": 0}
    assert admin.post("/api/trash/empty", json={}).json() == {"purged": 0}
    assert services_of(admin).repo.get_asset(p5) is not None
    assert lea.post("/api/trash/restore", json={"ids": [p5]}).json() == {"restored": 1}


def test_source_filter_and_file_name_search_only_use_sources_you_can_see(
    world: World, tmp_path: Path
) -> None:
    """QA A9: tom could probe the restricted source by id, or by a file name only it has."""
    admin, tom = world.clients["admin"], world.clients["tom"]
    restricted = _source_id(admin, "restricted")
    write_photo(tmp_path / "s3" / "secretname.jpg", seed=0)  # the same file as p1
    assert admin.post(f"/api/sources/{restricted}/scan").status_code == 202
    services_of(admin).worker.run_until_idle()
    assert asset_id_of(admin, restricted, "secretname.jpg") == world.ids["p1"]

    for params in ({"source_id": restricted}, {"q": "secretname"}):
        assert tom.get("/api/assets", params=params).json()["items"] == [], params
        assert tom.get("/api/assets/facets", params=params).json()["total"] == 0, params
    by_admin = admin.get("/api/assets", params={"q": "secretname"}).json()["items"]
    assert [a["id"] for a in by_admin] == [world.ids["p1"]]


def test_trashed_photos_keep_their_thumbnail_and_preview_for_those_who_see_them_in_the_trash(
    world: World,
) -> None:
    """QA A10: the trash page showed broken images."""
    admin, lea = world.clients["admin"], world.clients["lea"]
    p1, p5 = world.ids["p1"], world.ids["p5"]
    assert admin.request("DELETE", "/api/assets", json={"ids": [p1]}).json() == {"trashed": 1}
    assert lea.request("DELETE", "/api/assets", json={"ids": [p5]}).json() == {"trashed": 1}
    for kind in ("thumb", "preview"):
        assert admin.get(f"/api/assets/{p1}/{kind}").status_code == 200, kind
        assert lea.get(f"/api/assets/{p5}/{kind}").status_code == 200, kind
        assert admin.get(f"/api/assets/{p5}/{kind}").status_code == 404, "lea's private photo"
    assert admin.get(f"/api/assets/{p1}").status_code == 404, "still gone from the library"
    assert admin.get(f"/api/assets/{p1}/original").status_code == 404


def test_members_see_source_names_but_never_folder_paths(world: World) -> None:
    """QA A12: absolute folder paths on the server are the admin's business."""
    tom, admin = world.clients["tom"], world.clients["admin"]
    assert {s["path"] for s in tom.get("/api/sources").json()} == {None}
    assert all(s["path"].startswith("/") for s in admin.get("/api/sources").json())
