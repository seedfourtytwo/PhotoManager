"""A person's portrait over HTTP (issue 53, docs/contracts/api-v1.md "Local ML"): the server
cuts the round picture from the original with libvips; the browser only shows it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photo_assistant.domain.faces import BoundingBox, Face
from tests.api.conftest import add_user, asset_id_of, import_folder, refusal, services_of
from tests.conftest import snapshot_tree
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

FACE = BoundingBox(0.4, 0.3, 0.2, 0.2)  # 240 px wide on the landscape photo: a 480 px cut


@pytest.fixture
def lea(admin: TestClient, tmp_path: Path) -> dict[str, int]:
    """Lea on a landscape and a portrait photo (the first found is the cover); Tom on a third."""
    folder = tmp_path / "pics"
    write_photo(folder / "wide.jpg", seed=1, size=(1200, 900))
    write_photo(folder / "tall.jpg", seed=2, size=(900, 1200))
    write_photo(folder / "tom.jpg", seed=3, size=(1200, 900))
    source = import_folder(admin, folder, "Pics")
    ids = {n: asset_id_of(admin, source, f"{n}.jpg") for n in ("wide", "tall", "tom")}
    store = services_of(admin).ml.store
    faces = {
        f"f_{name}": store.replace_faces(ids[name], "f", [Face(FACE, score, (), (1.0, 0.0, 0.0))])[
            0
        ]
        for name, score in (("wide", 0.8), ("tall", 0.9), ("tom", 0.7))
    }
    person = store.create_person(faces["f_wide"])
    store.assign_face(faces["f_tall"], person)
    return ids | faces | {"lea": person, "tom_id": store.create_person(faces["f_tom"])}


def picture(client: TestClient, url: str, tmp_path: Path) -> Image.Image:
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/webp"
    target = tmp_path / "portrait.webp"
    target.write_bytes(response.content)
    with Image.open(target) as image:
        image.load()
        return image


def test_the_automatic_portrait_is_a_320_px_square_cut_from_the_original(
    admin: TestClient, lea: dict[str, int], tmp_path: Path
) -> None:
    person = admin.get(f"/api/people/{lea['lea']}").json()
    portrait = person["portrait"]
    assert (portrait["face_id"], portrait["asset_id"]) == (lea["f_wide"], lea["wide"])
    assert portrait["chosen"] is False
    assert portrait["size"] == pytest.approx(480 / 900), "twice the face, of the shorter edge"
    assert portrait["cx"] == pytest.approx(0.5) and portrait["cy"] < 0.4
    assert portrait["url"].startswith(f"/api/people/{lea['lea']}/portrait?v=")
    assert person["cover"]["id"] == lea["f_wide"], "the cover is still there"
    assert picture(admin, portrait["url"], tmp_path).size == (320, 320)
    (listed,) = (p for p in admin.get("/api/people").json() if p["id"] == lea["lea"])
    assert listed == person


def test_a_chosen_portrait_is_served_and_its_url_changes_with_it(
    admin: TestClient, lea: dict[str, int], tmp_path: Path
) -> None:
    services = services_of(admin)
    originals = services.store.absolute("originals")
    before_files = snapshot_tree(originals)
    before = admin.get(f"/api/people/{lea['lea']}").json()["portrait"]

    chosen = admin.put(
        f"/api/people/{lea['lea']}/portrait",
        json={"face_id": lea["f_tall"], "cx": 0.5, "cy": 0.5, "size": 0.6},
    )
    assert chosen.status_code == 200, chosen.text
    portrait = chosen.json()["portrait"]
    assert portrait == {
        "face_id": lea["f_tall"],
        "asset_id": lea["tall"],
        "cx": 0.5,
        "cy": 0.5,
        "size": 0.6,
        "chosen": True,
        "url": portrait["url"],
    }
    assert portrait["url"] != before["url"], "a new address, so no browser shows the old one"
    assert chosen.json()["cover"]["id"] == lea["f_tall"]
    assert admin.get(f"/api/people/{lea['lea']}").json() == chosen.json()
    assert picture(admin, portrait["url"], tmp_path).size == (320, 320), "540 px, shrunk"

    cleared = admin.delete(f"/api/people/{lea['lea']}/portrait")
    assert cleared.status_code == 200
    automatic = cleared.json()["portrait"]
    assert (automatic["chosen"], automatic["face_id"]) == (False, lea["f_tall"])
    assert automatic["url"] not in (portrait["url"], before["url"])
    assert picture(admin, automatic["url"], tmp_path).size == (320, 320)

    assert snapshot_tree(originals) == before_files, "originals are never written to"
    derived = services.store.absolute("derived/portrait")
    assert len(list(derived.rglob("*.webp"))) == 2, "the chosen cut went with the choice"


def test_a_small_face_is_never_blown_up(
    admin: TestClient, lea: dict[str, int], tmp_path: Path
) -> None:
    put = admin.put(
        f"/api/people/{lea['lea']}/portrait",
        json={"face_id": lea["f_wide"], "cx": 0.5, "cy": 0.5, "size": 0.2},
    )
    assert picture(admin, put.json()["portrait"]["url"], tmp_path).size == (180, 180)


def test_numbers_outside_the_photo_are_brought_inside(
    admin: TestClient, lea: dict[str, int]
) -> None:
    put = admin.put(
        f"/api/people/{lea['lea']}/portrait",
        json={"face_id": lea["f_wide"], "cx": -3, "cy": 8, "size": 40},
    )
    assert put.status_code == 200
    portrait = put.json()["portrait"]
    assert (portrait["cx"], portrait["cy"], portrait["size"]) == (pytest.approx(0.375), 0.5, 1.0)


def test_the_faces_to_choose_from_come_best_first_each_with_its_own_picture(
    admin: TestClient, lea: dict[str, int], tmp_path: Path
) -> None:
    faces = admin.get(f"/api/people/{lea['lea']}/faces").json()
    assert [f["face_id"] for f in faces] == [lea["f_tall"], lea["f_wide"]]
    assert [f["asset_id"] for f in faces] == [lea["tall"], lea["wide"]]
    assert all(f["chosen"] is False for f in faces)
    assert faces[0]["url"].startswith(f"/api/faces/{lea['f_tall']}/portrait?v=")
    assert faces[0]["size"] == pytest.approx(360 / 900), "a 180 px wide face on the tall photo"
    assert picture(admin, faces[0]["url"], tmp_path).size == (320, 320)
    one = admin.get(f"/api/people/{lea['lea']}/faces", params={"limit": 1}).json()
    assert [f["face_id"] for f in one] == [lea["f_tall"]]


def test_a_picture_is_cached_for_good_only_at_the_address_of_this_very_picture(
    admin: TestClient, lea: dict[str, int]
) -> None:
    url = admin.get(f"/api/people/{lea['lea']}").json()["portrait"]["url"]
    assert "immutable" in admin.get(url).headers["cache-control"]
    bare = admin.get(f"/api/people/{lea['lea']}/portrait")
    assert bare.status_code == 200 and bare.headers["cache-control"] == "no-store"
    stale = admin.get(f"/api/people/{lea['lea']}/portrait", params={"v": "old"})
    assert stale.headers["cache-control"] == "no-store"
    face = admin.get(f"/api/people/{lea['lea']}/faces").json()[0]["url"]
    assert "immutable" in admin.get(face).headers["cache-control"]
    assert admin.get(face.split("?")[0]).headers["cache-control"] == "no-store"


def test_guests_see_portraits_but_cannot_choose_them(
    admin: TestClient, lea: dict[str, int]
) -> None:
    gus = add_user(admin, "gus", "guest")
    body = {"face_id": lea["f_tall"], "cx": 0.5, "cy": 0.5, "size": 0.5}
    assert gus.put(f"/api/people/{lea['lea']}/portrait", json=body).status_code == 403
    assert gus.delete(f"/api/people/{lea['lea']}/portrait").status_code == 403
    assert gus.get(f"/api/people/{lea['lea']}").json()["portrait"]["chosen"] is False
    assert gus.get(f"/api/people/{lea['lea']}/portrait").status_code == 200
    assert len(gus.get(f"/api/people/{lea['lea']}/faces").json()) == 2

    member = add_user(admin, "mia")
    assert member.put(f"/api/people/{lea['lea']}/portrait", json=body).status_code == 200
    assert gus.get(f"/api/people/{lea['lea']}").json()["portrait"]["chosen"] is True
    assert member.delete(f"/api/people/{lea['lea']}/portrait").status_code == 200


def test_portrait_routes_need_a_login(anon: TestClient) -> None:
    for path in ("/api/people/1/portrait", "/api/people/1/faces", "/api/faces/1/portrait"):
        assert anon.get(path).status_code == 401
    assert anon.put("/api/people/1/portrait", json={}).status_code == 401
    assert anon.delete("/api/people/1/portrait").status_code == 401


def test_portrait_refusals_say_why(admin: TestClient, lea: dict[str, int]) -> None:
    person = f"/api/people/{lea['lea']}"
    body = {"face_id": lea["f_tall"], "cx": 0.5, "cy": 0.5, "size": 0.5}
    nobody = (404, {"detail": "no person 99"})
    assert refusal(admin.get("/api/people/99/portrait")) == nobody
    assert refusal(admin.get("/api/people/99/faces")) == nobody
    assert refusal(admin.put("/api/people/99/portrait", json=body)) == nobody
    assert refusal(admin.delete("/api/people/99/portrait")) == nobody
    assert refusal(admin.get("/api/faces/999/portrait")) == (404, {"detail": "no face 999"})

    toms = admin.put(f"{person}/portrait", json=body | {"face_id": lea["f_tom"]})
    assert refusal(toms) == (404, {"detail": f"no face {lea['f_tom']}"}), "someone else's face"
    missing = admin.put(f"{person}/portrait", json=body | {"face_id": 999})
    assert refusal(missing) == (404, {"detail": "no face 999"})
    not_a_number = admin.put(
        f"{person}/portrait",
        content=f'{{"face_id": {lea["f_tall"]}, "cx": NaN, "cy": 0.5, "size": 0.5}}',
        headers={"content-type": "application/json"},
    )
    assert refusal(not_a_number) == (
        422,
        {"detail": "a portrait needs numbers for its centre and its size"},
    )
    assert admin.get(person).json()["portrait"]["chosen"] is False, "nothing was kept"

    assert admin.put(f"{person}/portrait", json={"face_id": lea["f_tall"]}).status_code == 422
    assert admin.put(f"{person}/portrait", json=body | {"face_id": 10**30}).status_code == 422
    for limit in (0, 101):
        assert admin.get(f"{person}/faces", params={"limit": limit}).status_code == 422


def test_a_person_with_a_missing_original_still_answers_but_has_no_picture(
    admin: TestClient, lea: dict[str, int]
) -> None:
    services = services_of(admin)
    asset = services.repo.get_asset(lea["tom"])
    assert asset is not None
    services.store.absolute(asset.library_path).unlink()
    person = admin.get(f"/api/people/{lea['tom_id']}")
    assert person.status_code == 200
    gone = admin.get(person.json()["portrait"]["url"])
    assert refusal(gone) == (404, {"detail": "the original of this photo is missing"})
