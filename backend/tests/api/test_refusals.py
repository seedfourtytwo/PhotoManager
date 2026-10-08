"""What a refused request answers: the status and the sentence, whole. The web app shows the
sentence and the mock API repeats it, so neither may drift when the code behind it moves."""

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, asset_id_of, import_folder, refusal, user_id_of
from tests.synthetic import write_photo


def test_a_folder_that_cannot_be_listed_or_made(admin: TestClient, tmp_path: Path) -> None:
    pictures = tmp_path / "Pictures"
    pictures.mkdir()
    (pictures / "note.txt").write_text("x")

    missing = admin.get("/api/folders", params={"path": str(pictures / "2019")})
    assert refusal(missing) == (
        404,
        {"detail": f"folder not found on this machine: {pictures / '2019'}"},
    )
    a_file = admin.get("/api/folders", params={"path": str(pictures / "note.txt")})
    assert refusal(a_file) == (422, {"detail": f"{pictures / 'note.txt'} is not a folder"})

    taken = admin.post("/api/folders", json={"path": str(pictures)})
    assert refusal(taken) == (422, {"detail": f"{pictures} already exists"})
    orphan = admin.post("/api/folders", json={"path": str(tmp_path / "no" / "such")})
    assert refusal(orphan) == (
        422,
        {"detail": f"the folder it would be in does not exist: {tmp_path / 'no'}"},
    )


def test_a_folder_that_is_a_source_already(admin: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "Pictures"
    folder.mkdir()
    assert admin.post("/api/sources", json={"label": "a", "path": str(folder)}).status_code == 201
    again = admin.post("/api/sources", json={"label": "b", "path": str(folder)})
    assert refusal(again) == (409, {"detail": f"folder is already a source: {folder}"})


def test_a_cursor_that_was_not_handed_out(admin: TestClient) -> None:
    junk = admin.get("/api/assets", params={"cursor": "junk"})
    assert refusal(junk) == (400, {"detail": "invalid cursor: 'junk'"})


@pytest.fixture
def photos(admin: TestClient, tmp_path: Path) -> tuple[int, list[int]]:
    """A source with two photos: (source id, asset ids)."""
    folder = tmp_path / "photos"
    for n in range(2):
        write_photo(folder / f"p{n}.jpg", seed=n, taken=datetime(2020, 5, n + 1, 12))
    source = import_folder(admin, folder, "photos")
    return source, [asset_id_of(admin, source, f"p{n}.jpg") for n in range(2)]


@pytest.mark.integration
def test_what_a_role_or_an_access_level_does_not_allow(
    admin: TestClient, photos: tuple[int, list[int]]
) -> None:
    source, ids = photos
    lea, gus = add_user(admin, "lea"), add_user(admin, "gus", "guest")
    lea_id = user_id_of(admin, "lea")
    view_only = {"everyone": None, "users": [{"user_id": lea_id, "level": "view"}]}
    assert admin.put(f"/api/sources/{source}/access", json=view_only).is_success
    album = admin.post("/api/albums", json={"title": "Trip", "asset_ids": ids}).json()["id"]
    members = f"/api/albums/{album}/members"
    assert admin.put(members, json=[{"user_id": lea_id, "role": "viewer"}]).is_success

    def forbidden(sentence: str) -> tuple[int, object]:
        return 403, {"detail": sentence}

    assert refusal(lea.get("/api/users")) == forbidden("only an admin can do this")
    assert refusal(gus.post("/api/albums", json={"title": "x"})) == forbidden(
        "guests can view and download, not change anything"
    )
    assert refusal(lea.get(f"/api/assets/{ids[0]}/original")) == forbidden(
        "you need 'download' access for this"
    )
    assert refusal(lea.request("DELETE", "/api/assets", json={"ids": ids})) == forbidden(
        "you need 'edit' access for this"
    )
    assert refusal(lea.post(f"/api/albums/{album}/items", json={"asset_ids": ids})) == forbidden(
        "you can look at this album, not change it"
    )
    assert refusal(lea.delete(f"/api/albums/{album}")) == forbidden(
        "only the album's owner can do this"
    )
    print_request = {"trim": "a4-landscape", "theme": "quiet", "cover": True}
    assert refusal(lea.post(f"/api/albums/{album}/print/plan", json=print_request)) == forbidden(
        "printing needs 'download' access to every photo"
    )


@pytest.mark.integration
def test_an_album_order_that_lists_a_photo_twice(
    admin: TestClient, photos: tuple[int, list[int]]
) -> None:
    _, ids = photos
    album = admin.post("/api/albums", json={"title": "Trip", "asset_ids": ids}).json()["id"]
    twice = admin.put(f"/api/albums/{album}/order", json={"asset_ids": [ids[0], ids[0]]})
    assert refusal(twice) == (
        422,
        {"detail": "the order must list photos of this album, each once"},
    )
