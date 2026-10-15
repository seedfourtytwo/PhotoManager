"""Local-ML endpoints (docs/contracts/api-v1.md, "Local ML") through the real app.

Without model files everything still answers: search falls back to the core text search and
says why, status reports "models not installed". With (fake) models the semantic path ranks
within the visible set only.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.app.search import SemanticSearch, SimilarPhotos
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from tests.api.conftest import add_user, asset_id_of, import_folder, refusal, services_of
from tests.ml.fakes import FakeClip
from tests.ml.test_face_adapters import buffalo
from tests.ml.test_onnx_clip import make_clip_folder
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


@pytest.fixture
def library(admin: TestClient, tmp_path: Path) -> dict[str, int]:
    """Three photos: two from 2019 (one named 'beach'), one from 2021."""
    from datetime import datetime

    folder = tmp_path / "pics"
    write_photo(folder / "beach.jpg", seed=1, taken=datetime(2019, 7, 4, 12))
    write_photo(folder / "garden.jpg", seed=2, taken=datetime(2019, 8, 1, 9))
    write_photo(folder / "snow.jpg", seed=3, taken=datetime(2021, 1, 2, 10))
    source = import_folder(admin, folder, "Pics")
    return {n: asset_id_of(admin, source, f"{n}.jpg") for n in ("beach", "garden", "snow")}


def _ids(response_json: dict) -> list[int]:  # type: ignore[type-arg]
    return [i["id"] for i in response_json["items"]]


def _install_fake_clip(admin: TestClient, vectors: dict[int, tuple[float, ...]]) -> FakeClip:
    """Pretend the CLIP model is installed: store vectors, swap the text encoder."""
    ml = services_of(admin).ml
    clip = FakeClip(dim=3)
    for asset_id, vector in vectors.items():
        ml.store.save_clip(asset_id, clip.name, vector)
    ml.clip = clip  # type: ignore[assignment]
    ml.search = SemanticSearch(clip, ml.store)
    ml.similar = SimilarPhotos(ml.store, clip.name)
    return clip


# --- without models -------------------------------------------------------------------------


def test_status_says_models_are_not_installed(admin: TestClient, library: dict[str, int]) -> None:
    body = admin.get("/api/ml/status").json()
    assert body["clip"]["ready"] is False and body["faces"]["ready"] is False
    assert "just models" in body["clip"]["detail"]
    assert body["models_installed"] is False
    assert "embed_clip" not in body["counts"], "C31: no jobs queued without the model files"


def test_search_falls_back_to_text_search(admin: TestClient, library: dict[str, int]) -> None:
    body = admin.get("/api/search", params={"q": "beach"}).json()
    assert body["mode"] == "text"
    assert "models not installed" in body["detail"]
    assert _ids(body) == [library["beach"]]
    assert body["items"][0]["score"] is None


def test_search_facets_narrow_the_set(admin: TestClient, library: dict[str, int]) -> None:
    body = admin.get("/api/search", params={"q": "date:2019"}).json()
    assert body["mode"] == "filter"
    assert body["facets"] == [{"name": "date", "value": "2019"}]
    assert _ids(body) == [library["garden"], library["beach"]]
    month = admin.get("/api/search", params={"q": "date:2019-07"}).json()
    assert _ids(month) == [library["beach"]]
    day = admin.get("/api/search", params={"q": "date:2021-01-02"}).json()
    assert _ids(day) == [library["snow"]]


def test_search_combines_facets_and_text(admin: TestClient, library: dict[str, int]) -> None:
    body = admin.get("/api/search", params={"q": "date:2021 beach"}).json()
    assert body["text"] == "beach" and _ids(body) == []


def test_similar_needs_the_model(admin: TestClient, library: dict[str, int]) -> None:
    response = admin.get(f"/api/assets/{library['beach']}/similar")
    assert response.status_code == 503
    assert "models not installed" in response.json()["detail"]


def test_faces_tags_and_people_are_empty_not_errors(
    admin: TestClient, library: dict[str, int]
) -> None:
    beach = library["beach"]
    assert admin.get(f"/api/assets/{beach}/faces").json() == []
    assert admin.get(f"/api/assets/{beach}/tags").json() == {
        "tags": [],
        "screen_or_document": None,
    }
    assert admin.get("/api/people").json() == []
    assert admin.get("/api/people/99").status_code == 404
    assert admin.get("/api/assets/9999/faces").status_code == 404


def test_backfill_is_admin_only(admin: TestClient, library: dict[str, int]) -> None:
    lea = add_user(admin, "lea")
    assert lea.post("/api/ml/backfill").status_code == 403
    body = admin.post("/api/ml/backfill").json()
    assert body["queued"] == 0, "nothing to queue until the model files are there (C31)"
    assert "models not installed" in body["detail"]


def test_ml_routes_need_a_login(anon: TestClient) -> None:
    for path in ("/api/search?q=x", "/api/people", "/api/ml/status"):
        assert anon.get(path).status_code == 401


# --- with (fake) models ---------------------------------------------------------------------


def test_semantic_search_ranks_by_meaning(admin: TestClient, library: dict[str, int]) -> None:
    clip = _install_fake_clip(
        admin,
        {library["beach"]: (1.0, 0.0, 0.0), library["garden"]: (0.0, 1.0, 0.0),
         library["snow"]: (0.7, 0.7, 0.0)},
    )  # fmt: skip
    clip.texts["sea"] = (1.0, 0.0, 0.0)
    body = admin.get("/api/search", params={"q": "sea"}).json()
    assert body["mode"] == "semantic" and body["detail"] is None
    assert _ids(body)[:2] == [library["beach"], library["snow"]]
    assert body["items"][0]["score"] == pytest.approx(1.0)
    narrowed = admin.get("/api/search", params={"q": "sea date:2019"}).json()
    assert set(_ids(narrowed)) == {library["beach"], library["garden"]}


def test_similar_photos_with_the_model(admin: TestClient, library: dict[str, int]) -> None:
    _install_fake_clip(admin, {library["beach"]: (1.0, 0.0, 0.0), library["snow"]: (0.9, 0.1, 0.0)})
    body = admin.get(f"/api/assets/{library['beach']}/similar").json()
    assert body[0]["id"] == library["snow"]
    garden = admin.get(f"/api/assets/{library['garden']}/similar")
    assert garden.status_code == 409, "not analysed yet"


# --- names in the words ---------------------------------------------------------------------


def _name_person(admin: TestClient, name: str, *asset_ids: int) -> int:
    store = services_of(admin).ml.store
    face = Face(BoundingBox(0.1, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))
    first, *others = (store.replace_faces(i, "f", [face])[0] for i in asset_ids)
    person = store.create_person(first)
    for face_id in others:
        store.assign_face(face_id, person)
    admin.patch(f"/api/people/{person}", json={"name": name})
    return person


def test_a_persons_name_in_the_words_narrows_like_the_facet(
    admin: TestClient, library: dict[str, int]
) -> None:
    clip = _install_fake_clip(
        admin,
        {library["beach"]: (0.0, 1.0, 0.0), library["garden"]: (1.0, 0.0, 0.0),
         library["snow"]: (1.0, 0.0, 0.0)},
    )  # fmt: skip
    clip.texts["sea"] = (1.0, 0.0, 0.0)
    _name_person(admin, "Léa", library["beach"], library["garden"])
    body = admin.get("/api/search", params={"q": "lea sea"}).json()
    assert body["mode"] == "semantic" and body["text"] == "sea"
    assert body["facets"] == [{"name": "person", "value": "Léa"}]
    assert _ids(body) == [library["garden"], library["beach"]], "Léa's photos, sea first"


def test_without_models_a_persons_name_alone_lists_their_photos(
    admin: TestClient, library: dict[str, int]
) -> None:
    _name_person(admin, "Lea Martin", library["snow"])
    body = admin.get("/api/search", params={"q": "Lea Martin"}).json()
    assert (body["mode"], _ids(body)) == ("filter", [library["snow"]])
    words = admin.get("/api/search", params={"q": "lea martin snow"}).json()
    assert (words["mode"], words["text"], _ids(words)) == ("text", "snow", [library["snow"]])


def test_a_place_name_in_the_words_narrows_like_the_facet(
    admin: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "trip"
    write_photo(folder / "paris.jpg", seed=7, gps=(48.8566, 2.3522))
    write_photo(folder / "home.jpg", seed=8)
    source = import_folder(admin, folder, "Trip")
    paris, home = (asset_id_of(admin, source, f"{n}.jpg") for n in ("paris", "home"))
    clip = _install_fake_clip(admin, {paris: (0.0, 1.0, 0.0), home: (1.0, 0.0, 0.0)})
    clip.texts["evening in"] = (1.0, 0.0, 0.0)
    body = admin.get("/api/search", params={"q": "evening in paris"}).json()
    assert body["facets"] == [{"name": "place", "value": "Paris"}]
    assert (body["text"], _ids(body)) == ("evening in", [paris])


def test_photos_in_an_album_named_in_the_words_come_first(
    admin: TestClient, library: dict[str, int]
) -> None:
    clip = _install_fake_clip(
        admin,
        {library["beach"]: (1.0, 0.0, 0.0), library["garden"]: (0.0, 1.0, 0.0),
         library["snow"]: (0.6, 0.8, 0.0)},
    )  # fmt: skip
    clip.texts["summer holidays"] = (1.0, 0.0, 0.0)
    album = [library["garden"], library["snow"]]
    admin.post("/api/albums", json={"title": "Summer Holidays", "asset_ids": album})
    body = admin.get("/api/search", params={"q": "summer holidays"}).json()
    assert body["mode"] == "semantic" and body["facets"] == []
    assert _ids(body) == [library["snow"], library["garden"], library["beach"]]
    first = admin.get("/api/search", params={"q": "summer holidays", "limit": 1}).json()
    assert _ids(first) == [library["snow"]]


def test_photos_with_a_tag_named_in_the_words_come_first(
    admin: TestClient, library: dict[str, int]
) -> None:
    clip = _install_fake_clip(
        admin, {library["beach"]: (1.0, 0.0, 0.0), library["snow"]: (0.0, 1.0, 0.0)}
    )
    clip.texts["snow"] = (1.0, 0.0, 0.0)
    services_of(admin).ml.store.replace_model_tags(
        library["snow"], clip.name, [TagScore("snow", 0.1)], False
    )
    body = admin.get("/api/search", params={"q": "snow"}).json()
    assert _ids(body) == [library["snow"], library["beach"]]


def test_a_named_photo_not_analysed_yet_is_still_found(
    admin: TestClient, library: dict[str, int]
) -> None:
    clip = _install_fake_clip(
        admin, {library["beach"]: (1.0, 0.0, 0.0), library["snow"]: (0.0, 1.0, 0.0)}
    )
    clip.texts["trip"] = (1.0, 0.0, 0.0)
    admin.post("/api/albums", json={"title": "Trip", "asset_ids": [library["garden"], library["snow"]]})
    body = admin.get("/api/search", params={"q": "trip"}).json()
    assert _ids(body) == [library["snow"], library["garden"], library["beach"]]
    assert [i["score"] is None for i in body["items"]] == [False, True, False]


def test_people_rename_merge_split_and_their_photos(
    admin: TestClient, library: dict[str, int]
) -> None:
    store = services_of(admin).ml.store
    box = BoundingBox(0.1, 0.1, 0.2, 0.2)
    faces = {
        name: store.replace_faces(
            library[name], "f", [Face(box, 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))]
        )[0]
        for name in library
    }
    lea = store.create_person(faces["beach"])
    store.assign_face(faces["garden"], lea)
    tom = store.create_person(faces["snow"])

    people = admin.get("/api/people").json()
    assert sorted(p["face_count"] for p in people) == [1, 2]
    renamed = admin.patch(f"/api/people/{lea}", json={"name": "Lea"}).json()
    assert renamed["name"] == "Lea" and renamed["cover"]["asset_id"] in library.values()
    assets = admin.get(f"/api/people/{lea}/assets").json()
    assert _ids(assets) == [library["garden"], library["beach"]]
    assert admin.get("/api/search", params={"q": "person:Lea"}).json()["mode"] == "filter"
    assert _ids(admin.get("/api/search", params={"q": "person:lea"}).json()) == _ids(assets)

    merged = admin.post(f"/api/people/{lea}/merge", json={"source_ids": [tom]}).json()
    assert merged["face_count"] == 3
    split = admin.post("/api/people/split", json={"face_ids": [faces["snow"]], "name": "Tom"})
    assert split.status_code == 200 and split.json()["name"] == "Tom"
    faces_of_snow = admin.get(f"/api/assets/{library['snow']}/faces").json()
    assert faces_of_snow[0]["person_id"] == split.json()["id"]


def test_a_person_is_hidden_from_people_and_shown_again(
    admin: TestClient, library: dict[str, int]
) -> None:
    store = services_of(admin).ml.store
    face = Face(BoundingBox(0.1, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))
    lea = store.create_person(store.replace_faces(library["beach"], "f", [face])[0])
    tom = store.create_person(store.replace_faces(library["snow"], "f", [face])[0])
    admin.patch(f"/api/people/{tom}", json={"name": "Tom"})

    hidden = admin.patch(f"/api/people/{tom}", json={"hidden": True})
    assert hidden.status_code == 200
    assert (hidden.json()["hidden"], hidden.json()["name"]) == (True, "Tom"), "the name stays"
    assert [(p["id"], p["hidden"]) for p in admin.get("/api/people").json()] == [(lea, False)]
    listed = admin.get("/api/people", params={"hidden": "true"}).json()
    assert [(p["id"], p["hidden"]) for p in listed] == [(tom, True)]
    assert admin.get(f"/api/people/{tom}").json()["hidden"] is True
    by_name = admin.get("/api/search", params={"q": "person:Tom"}).json()
    assert _ids(by_name) == [library["snow"]], "a hidden person is still found by name"

    renamed = admin.patch(f"/api/people/{tom}", json={"name": None}).json()
    assert (renamed["name"], renamed["hidden"]) == (None, True), "a rename leaves it hidden"
    shown = admin.patch(f"/api/people/{tom}", json={"hidden": False}).json()
    assert shown["hidden"] is False
    assert {p["id"] for p in admin.get("/api/people").json()} == {lea, tom}
    assert admin.patch(f"/api/people/{tom}", json={}).status_code == 422, "nothing to change"


def test_people_and_face_ids_beyond_sqlite_integers_are_unprocessable(
    admin: TestClient, library: dict[str, int]
) -> None:
    store = services_of(admin).ml.store
    face = Face(BoundingBox(0.1, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))
    (face_id,) = store.replace_faces(library["beach"], "f", [face])
    lea = store.create_person(face_id)
    huge = 10**30
    for path, body in (
        (f"/api/people/{lea}/merge", {"source_ids": [huge]}),
        ("/api/people/split", {"face_ids": [huge]}),
        ("/api/people/split", {"face_ids": [face_id], "person_id": huge}),
    ):
        assert admin.post(path, json=body).status_code == 422, (path, body)


def test_guests_cannot_change_people(admin: TestClient, library: dict[str, int]) -> None:
    gus = add_user(admin, "gus", "guest")
    assert gus.patch("/api/people/1", json={"name": "x"}).status_code == 403
    assert gus.patch("/api/people/1", json={"hidden": True}).status_code == 403
    assert gus.post("/api/people/split", json={"face_ids": [1]}).status_code == 403


def test_search_and_similar_refusals_say_why(admin: TestClient, library: dict[str, int]) -> None:
    impossible = admin.get("/api/search", params={"q": "date:2023-02-30"})
    assert refusal(impossible) == (400, {"detail": "date:2023-02-30 is not a real date"})
    _install_fake_clip(admin, {library["beach"]: (1.0, 0.0, 0.0)})
    waiting = admin.get(f"/api/assets/{library['garden']}/similar")
    assert refusal(waiting) == (409, {"detail": "this photo has not been analysed yet"})


def test_people_refusals_say_why(admin: TestClient, library: dict[str, int]) -> None:
    store = services_of(admin).ml.store
    face = Face(BoundingBox(0.1, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, (1.0, 0.0, 0.0))
    (face_id,) = store.replace_faces(library["beach"], "f", [face])
    lea = store.create_person(face_id)
    nobody = (404, {"detail": "no person 99"})
    assert refusal(admin.get("/api/people/99")) == nobody
    assert refusal(admin.patch("/api/people/99", json={"name": "x"})) == nobody
    assert refusal(admin.get("/api/people/99/assets")) == nobody
    assert refusal(admin.post("/api/people/99/merge", json={"source_ids": [lea]})) == nobody
    assert refusal(admin.post(f"/api/people/{lea}/merge", json={"source_ids": [99]})) == nobody
    itself = admin.post(f"/api/people/{lea}/merge", json={"source_ids": [lea]})
    assert refusal(itself) == (422, {"detail": "cannot merge a person into itself"})

    split = "/api/people/split"
    none = admin.post(split, json={"face_ids": []})
    assert refusal(none) == (422, {"detail": "choose at least one face to move"})
    stranger = admin.post(split, json={"face_ids": [999]})
    assert refusal(stranger) == (404, {"detail": "no face 999"})
    assert refusal(admin.post(split, json={"face_ids": [face_id], "person_id": 99})) == nobody
    long_name = admin.post(split, json={"face_ids": [face_id], "name": "x" * 101})
    assert refusal(long_name) == (422, {"detail": "name too long (max 100 characters)"})
    renamed = admin.patch(f"/api/people/{lea}", json={"name": "x" * 101})
    assert refusal(renamed) == (422, {"detail": "name too long (max 100 characters)"})


def test_preview_jobs_plan_ml_analysis_after_import_only_with_models(
    admin: TestClient, library: dict[str, int]
) -> None:
    kinds = {j["kind"] for j in services_of(admin).repo.list_jobs()}
    assert not {"embed_clip", "detect_faces", "auto_tag"} & kinds, "no models: nothing planned"
    services = services_of(admin)
    models = services.settings.ml.models_root(services.settings.data_root)
    make_clip_folder(models / "clip" / services.settings.ml.clip_model)  # tiny synthetic models
    buffalo(models / "insightface" / "buffalo_l")
    services.ml.planner.for_asset(library["beach"])
    kinds = {j["kind"] for j in services.repo.list_jobs("queued")}
    assert {"embed_clip", "detect_faces", "auto_tag"} <= kinds
