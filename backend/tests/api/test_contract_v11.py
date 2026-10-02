"""Contract v1.1: what the web app needs beyond v1 (docs/wiring/web.md, "Asks for the backend")."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.api.conftest import BASE, add_user, asset_id_of, import_folder, user_id_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


@pytest.fixture
def photo(admin: TestClient, tmp_path: Path) -> int:
    folder = tmp_path / "pics"
    write_photo(folder / "wide.jpg", seed=1, size=(300, 200))
    source = import_folder(admin, folder, "Pics")
    return asset_id_of(admin, source, "wide.jpg")


def _size(content: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(content)) as image:
        return image.size


# --- ZIP download posted as a form (the browser streams it straight to disk) ----------------


def test_a_zip_can_be_posted_as_a_form_field_holding_json(admin: TestClient, photo: int) -> None:
    request = {"ids": [photo], "format": "jpeg", "max_edge": 100}
    response = admin.post(
        "/api/downloads",
        data={"request": json.dumps(request)},
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        (name,) = archive.namelist()
        assert name == "wide.jpg"
        assert _size(archive.read(name)) == (100, 67)


def test_the_json_body_still_works(admin: TestClient, photo: int) -> None:
    response = admin.post("/api/downloads", json={"ids": [photo]})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["wide.jpg"]


@pytest.mark.parametrize(
    "data",
    [{}, {"request": "not json"}, {"request": json.dumps({"ids": [1], "format": "gif"})}],
)
def test_a_broken_form_is_422(admin: TestClient, photo: int, data: dict[str, str]) -> None:
    assert admin.post("/api/downloads", data=data).status_code == 422


def test_a_cross_site_form_post_is_refused(admin: TestClient, photo: int) -> None:
    response = admin.post(
        "/api/downloads",
        data={"request": json.dumps({"ids": [photo]})},
        headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
    )
    assert response.status_code == 403


# --- the editor's base image ------------------------------------------------------------------


def test_preview_with_edit_none_is_the_unedited_photo(admin: TestClient, photo: int) -> None:
    turn = {"rotate": 90, "flip_horizontal": False, "flip_vertical": False, "crop": None,
            "straighten": 0}  # fmt: skip
    assert admin.put(f"/api/assets/{photo}/edit", json=turn).status_code == 200
    edited = admin.get(f"/api/assets/{photo}/preview")
    plain = admin.get(f"/api/assets/{photo}/preview", params={"edit": "none"})
    assert _size(edited.content) == (200, 300)
    assert _size(plain.content) == (300, 200)
    assert admin.get(f"/api/assets/{photo}/preview", params={"edit": "x"}).status_code == 422


# --- a user directory for sharing albums -----------------------------------------------------


def test_members_see_active_names_admins_see_everyone(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    add_user(admin, "tom")
    admin.patch(f"/api/users/{user_id_of(admin, 'tom')}", json={"disabled": True})

    seen_by_lea = lea.get("/api/users/directory").json()
    assert seen_by_lea == [
        {"id": 1, "display_name": "C"},
        {"id": user_id_of(admin, "lea"), "display_name": "Lea"},
    ]
    assert {u["display_name"] for u in admin.get("/api/users/directory").json()} == {
        "C",
        "Lea",
        "Tom",
    }
    assert set(seen_by_lea[0]) == {"id", "display_name"}, "no usernames or roles"


def test_guests_and_strangers_get_no_directory(admin: TestClient) -> None:
    gus = add_user(admin, "gus", "guest")
    assert gus.get("/api/users/directory").status_code == 403
    assert TestClient(admin.app, base_url=BASE).get("/api/users/directory").status_code == 401


def test_an_album_owner_can_share_using_the_directory(admin: TestClient, photo: int) -> None:
    lea = add_user(admin, "lea")
    tom = add_user(admin, "tom")
    album = lea.post("/api/albums", json={"title": "Ours"}).json()
    tom_entry = next(
        u for u in lea.get("/api/users/directory").json() if u["display_name"] == "Tom"
    )
    shared = lea.put(
        f"/api/albums/{album['id']}/members", json=[{"user_id": tom_entry["id"], "role": "viewer"}]
    )
    assert shared.status_code == 200
    assert [a["title"] for a in tom.get("/api/albums").json()] == ["Ours"]


def test_taken_at_is_wall_clock_to_the_second(admin: TestClient, tmp_path: Path) -> None:
    """Contract: `2019-07-04T18:30:00`. Dates guessed from a file's mtime had microseconds."""
    import os
    import re

    folder = tmp_path / "noexif"
    path = write_photo(folder / "x.jpg", seed=5)
    os.utime(path, ns=(1_700_000_000_123_456_789, 1_700_000_000_123_456_789))
    import_folder(admin, folder, "No EXIF")
    (item,) = admin.get("/api/assets").json()["items"]
    assert item["date_source"] == "file_mtime"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", item["taken_at"]), item["taken_at"]
    detail = admin.get(f"/api/assets/{item['id']}").json()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", detail["taken_at"])
