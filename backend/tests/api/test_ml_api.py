"""Local-ML endpoints (docs/wiring/ml.md) through the real app.

Without model files everything still answers: search falls back to the core text search and
says why, status reports "models not installed". With (fake) models the semantic path ranks
within the visible set only.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.app.search import SemanticSearch, SimilarPhotos
from photo_assistant.domain.faces import BoundingBox, Face
from tests.api.conftest import add_user, asset_id_of, import_folder, services_of
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


def test_guests_cannot_change_people(admin: TestClient, library: dict[str, int]) -> None:
    gus = add_user(admin, "gus", "guest")
    assert gus.patch("/api/people/1", json={"name": "x"}).status_code == 403
    assert gus.post("/api/people/split", json={"face_ids": [1]}).status_code == 403


@pytest.mark.skipif(shutil.which("vips") is None, reason="needs libvips")
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
