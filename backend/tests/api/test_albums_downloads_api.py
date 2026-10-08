"""Albums (members, roles, order, cover) and downloads (ZIP, single file, options)."""

import io
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photo_assistant.adapters.exiftool_reader import ExifToolReader
from photo_assistant.domain.access import Viewer
from tests.api.conftest import add_user, asset_id_of, import_folder, services_of, user_id_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


@pytest.fixture
def ids(admin: TestClient, tmp_path: Path) -> list[int]:
    folder = tmp_path / "photos"
    for n in range(4):
        write_photo(
            folder / f"IMG_{n}.jpg",
            seed=n * 11,
            size=(400, 300),
            taken=datetime(2019 + n % 2, 7, n + 1, 12, 0),
            gps=(48.85, 2.35),
            camera=f"Cam {n}",
        )
    source = import_folder(admin, folder, "photos")
    return [asset_id_of(admin, source, f"IMG_{n}.jpg") for n in range(4)]


def item_ids(client: TestClient, album_id: int) -> list[int]:
    return [i["id"] for i in client.get(f"/api/albums/{album_id}").json()["items"]]


def test_album_lifecycle(admin: TestClient, ids: list[int]) -> None:
    created = admin.post(
        "/api/albums",
        json={"title": "Trip", "description": "Brittany", "asset_ids": [ids[0], ids[1], 999]},
    )
    assert created.status_code == 201
    album = created.json()
    assert album["count"] == 2 and album["role"] == "owner"
    assert album["cover"]["url"] == f"/api/assets/{ids[0]}/thumb?v=0", "first photo by default"
    a = album["id"]
    assert admin.post(
        f"/api/albums/{a}/items", json={"asset_ids": [ids[2], ids[0]], "position": 0}
    ).json() == {"count": 1}
    assert item_ids(admin, a) == [ids[2], ids[0], ids[1]]
    assert (
        admin.put(
            f"/api/albums/{a}/order", json={"asset_ids": [ids[1], ids[0], ids[2]]}
        ).status_code
        == 204
    )
    assert item_ids(admin, a) == [ids[1], ids[0], ids[2]]
    assert admin.put(f"/api/albums/{a}/order", json={"asset_ids": [ids[3]]}).status_code == 422
    patched = admin.patch(f"/api/albums/{a}", json={"title": "Trip 2019", "cover_asset_id": ids[2]})
    assert patched.json()["title"] == "Trip 2019"
    assert patched.json()["cover"]["url"].startswith(f"/api/assets/{ids[2]}/thumb")
    bad_cover = admin.patch(f"/api/albums/{a}", json={"cover_asset_id": ids[3]})
    assert bad_cover.status_code == 422
    removed = admin.request("DELETE", f"/api/albums/{a}/items", json={"asset_ids": [ids[2]]})
    assert removed.json() == {"count": 1}
    assert (
        admin.get(f"/api/albums/{a}").json()["cover"]["url"].startswith(f"/api/assets/{ids[1]}/")
    ), "cover falls back when its photo leaves"
    detail = admin.get(f"/api/assets/{ids[0]}").json()
    assert detail["albums"] == [{"id": a, "title": "Trip 2019"}]
    assert admin.delete(f"/api/albums/{a}").status_code == 204
    assert admin.get(f"/api/albums/{a}").status_code == 404
    assert admin.get(f"/api/assets/{ids[0]}").status_code == 200, "photos stay"


def test_members_and_roles(admin: TestClient, ids: list[int]) -> None:
    lea, tom, gus = add_user(admin, "lea"), add_user(admin, "tom"), add_user(admin, "gus", "guest")
    tom_id, gus_id = user_id_of(admin, "tom"), user_id_of(admin, "gus")
    a = lea.post("/api/albums", json={"title": "Shared", "asset_ids": [ids[0]]}).json()["id"]
    assert tom.get(f"/api/albums/{a}").status_code == 404, "not shared yet"
    members = [{"user_id": tom_id, "role": "editor"}, {"user_id": gus_id, "role": "editor"}]
    assert lea.put(f"/api/albums/{a}/members", json=members).json() == members
    assert tom.get(f"/api/albums/{a}/members").json() == members
    assert tom.post(f"/api/albums/{a}/items", json={"asset_ids": [ids[1]]}).json() == {"count": 1}
    assert tom.put(f"/api/albums/{a}/members", json=[]).status_code == 403, "owner only"
    assert tom.delete(f"/api/albums/{a}").status_code == 403
    assert gus.post(f"/api/albums/{a}/items", json={"asset_ids": [ids[2]]}).status_code == 403
    assert gus.post("/api/albums", json={"title": "x"}).status_code == 403
    viewer = [{"user_id": tom_id, "role": "viewer"}]
    lea.put(f"/api/albums/{a}/members", json=viewer)
    assert tom.patch(f"/api/albums/{a}", json={"title": "no"}).status_code == 403
    assert [x["role"] for x in tom.get("/api/albums").json()] == ["viewer"]
    lea_id = user_id_of(admin, "lea")
    owner_as_member = lea.put(
        f"/api/albums/{a}/members", json=[{"user_id": lea_id, "role": "editor"}]
    )
    assert owner_as_member.status_code == 422
    unknown = lea.put(f"/api/albums/{a}/members", json=[{"user_id": 999, "role": "viewer"}])
    assert unknown.status_code == 422
    assert admin.patch(f"/api/albums/{a}", json={"description": "admin may"}).status_code == 200


def zip_names(response_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(response_bytes)) as z:
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        return z.namelist()


def test_zip_of_originals_by_ids_album_and_filter(admin: TestClient, ids: list[int]) -> None:
    body = {"ids": ids[:2], "format": "original", "folders": "year"}
    estimate = admin.post("/api/downloads/estimate", json=body).json()
    assert estimate["count"] == 2 and estimate["bytes"] > 0
    response = admin.post("/api/downloads", json=body)
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-skipped"] == "0"
    assert sorted(zip_names(response.content)) == ["2019/IMG_0.jpg", "2020/IMG_1.jpg"]
    album = admin.post("/api/albums", json={"title": "A", "asset_ids": [ids[3]]}).json()["id"]
    by_album = admin.post(
        "/api/downloads", json={"album_id": album, "naming": "date", "folders": "month"}
    )
    assert zip_names(by_album.content) == ["2020/07/2020-07-04_120000_Paris.jpg"]
    by_filter = admin.post("/api/downloads", json={"filters": {"year": 2019}})
    assert sorted(zip_names(by_filter.content)) == ["IMG_0.jpg", "IMG_2.jpg"]
    assert admin.post("/api/downloads", json={"ids": ids, "album_id": album}).status_code == 422
    assert admin.post("/api/downloads", json={"album_id": 999}).status_code == 404
    assert admin.post("/api/downloads", json={"filters": {"month": 3}}).status_code == 400


def test_zip_converts_resizes_and_strips(admin: TestClient, ids: list[int], tmp_path: Path) -> None:
    body = {"ids": [ids[0]], "format": "png", "max_edge": 100, "strip_all_metadata": True}
    small = admin.post("/api/downloads/estimate", json=body).json()["bytes"]
    body_big = body | {"max_edge": None}
    assert small < admin.post("/api/downloads/estimate", json=body_big).json()["bytes"]
    content = admin.post("/api/downloads", json=body).content
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        (name,) = z.namelist()
        data = z.read(name)
    assert name == "IMG_0.png"
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "PNG" and im.size == (100, 75)
    loc = admin.post("/api/downloads", json={"ids": [ids[0]], "strip_location": True})
    with zipfile.ZipFile(io.BytesIO(loc.content)) as z:
        out = tmp_path / "out.jpg"
        out.write_bytes(z.read("IMG_0.jpg"))
    reader = ExifToolReader()
    try:
        (meta,) = reader.read_many([out])
    finally:
        reader.close()
    assert meta.latitude is None and meta.camera_model == "Cam 0"
    assert not list((tmp_path / "data" / "tmp").glob("download-*")), "temp copies cleaned up"


def test_a_zip_looks_up_its_file_names_once_and_an_estimate_not_at_all(
    admin: TestClient, ids: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One lookup per photo held the database for the whole selection before the first byte."""
    repo = services_of(admin).repo
    lookups: list[int] = []
    batched = repo.first_origin_names

    def counted(viewer: Viewer, asset_ids: Sequence[int]) -> dict[int, str]:
        lookups.append(len(asset_ids))
        return batched(viewer, asset_ids)

    monkeypatch.setattr(repo, "first_origin_names", counted)
    estimate = admin.post("/api/downloads/estimate", json={"ids": ids}).json()
    assert estimate["count"] == 4 and estimate["bytes"] > 0
    assert lookups == [], "an estimate needs no file names"
    response = admin.post("/api/downloads", json={"ids": ids})
    assert len(zip_names(response.content)) == 4
    assert lookups == [4]


def test_stripping_an_original_copies_it_without_loading_it_into_memory(
    admin: TestClient, ids: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(path: Path) -> bytes:
        raise AssertionError(f"{path.name} was read into memory in one piece")

    monkeypatch.setattr(Path, "read_bytes", refuse)
    response = admin.post("/api/downloads", json={"ids": [ids[0]], "strip_location": True})
    monkeypatch.undo()
    assert zip_names(response.content) == ["IMG_0.jpg"]


def test_single_download(admin: TestClient, ids: list[int]) -> None:
    original = admin.get(f"/api/assets/{ids[0]}/download")
    assert original.status_code == 200 and original.headers["content-type"] == "image/jpeg"
    assert 'filename="IMG_0.jpg"' in original.headers["content-disposition"]
    webp = admin.get(
        f"/api/assets/{ids[0]}/download", params={"format": "webp", "max_edge": 50, "quality": 50}
    )
    assert webp.headers["content-type"] == "image/webp"
    assert "IMG_0.webp" in webp.headers["content-disposition"]
    with Image.open(io.BytesIO(webp.content)) as im:
        assert im.size == (50, 38)
    assert admin.get(f"/api/assets/{ids[0]}/download", params={"format": "gif"}).status_code == 422
    admin.put(f"/api/assets/{ids[1]}/edit", json={"rotate": 90})
    turned = admin.get(f"/api/assets/{ids[1]}/download", params={"format": "jpeg"})
    with Image.open(io.BytesIO(turned.content)) as im:
        assert im.size == (300, 400), "the edit is applied to rendered downloads"
    untouched = admin.get(f"/api/assets/{ids[1]}/download")
    with Image.open(io.BytesIO(untouched.content)) as im:
        assert im.size == (400, 300), "original means untouched"


def test_an_absurd_max_edge_is_refused(admin: TestClient, ids: list[int]) -> None:
    """QA A6: max_edge=10**9 overflowed libvips."""
    body = {"ids": ids, "format": "jpeg", "max_edge": 10**9}
    assert admin.post("/api/downloads", json=body).status_code == 422
    assert admin.post("/api/downloads/estimate", json=body).status_code == 422
    one = admin.get(f"/api/assets/{ids[0]}/download", params={"format": "jpeg", "max_edge": 10**9})
    assert one.status_code == 422


def test_a_photo_that_fails_is_left_out_of_the_zip_and_listed_in_its_manifest(
    admin: TestClient, ids: list[int]
) -> None:
    """QA A6: one failing photo used to cut the ZIP short (a truncated, unreadable archive)."""
    from tests.api.conftest import services_of

    services = services_of(admin)
    broken = services.repo.get_asset(ids[1])
    assert broken is not None
    library_file = services.store.absolute(broken.library_path)
    library_file.chmod(0o644)
    library_file.write_bytes(b"not a photo any more")  # synthetic test library only
    for fmt in ("original", "jpeg"):
        body = {"ids": ids, "format": fmt} | ({"strip_location": True} if fmt == "original" else {})
        if fmt == "original":
            library_file.unlink()
        response = admin.post("/api/downloads", json=body)
        assert response.status_code == 200
        names = zip_names(response.content)
        assert "manifest.txt" in names, fmt
        assert len([n for n in names if n != "manifest.txt"]) == 3
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            manifest = z.read("manifest.txt").decode()
        assert "1 photo could not be included" in manifest and "IMG_1" in manifest
    fine = admin.post("/api/downloads", json={"ids": [ids[0]], "format": "jpeg"})
    assert zip_names(fine.content) == ["IMG_0.jpg"], "no manifest when nothing failed"


@pytest.mark.parametrize("fmt", ["original", "jpeg", "webp", "png"])
@pytest.mark.parametrize("max_edge", [None, 200])
def test_size_estimates_are_within_a_factor_of_two_of_the_real_files(
    admin: TestClient, ids: list[int], fmt: str, max_edge: int | None
) -> None:
    """QA A14 (E2E): estimates were 10 to 30 times too high."""
    body = {"ids": ids, "format": fmt, "max_edge": max_edge}
    estimate = admin.post("/api/downloads/estimate", json=body).json()["bytes"]
    with zipfile.ZipFile(io.BytesIO(admin.post("/api/downloads", json=body).content)) as z:
        actual = sum(i.file_size for i in z.infolist())
    assert actual / 2 <= estimate <= actual * 2, (estimate, actual)


# --- QA A15: "Remove from album" -> Undo puts the photos back where they were -------------------


def test_undo_of_a_removal_restores_the_order_and_the_cover(
    admin: TestClient, ids: list[int]
) -> None:
    a, b, c, d = ids
    album = admin.post("/api/albums", json={"title": "T", "asset_ids": ids}).json()["id"]
    assert admin.patch(f"/api/albums/{album}", json={"cover_asset_id": b}).is_success
    admin.request("DELETE", f"/api/albums/{album}/items", json={"asset_ids": [b, d]})
    assert item_ids(admin, album) == [a, c]
    # undo: put each photo back at the index it had, smallest first
    for asset_id, position in ((b, 1), (d, 3)):
        added = admin.post(
            f"/api/albums/{album}/items", json={"asset_ids": [asset_id], "position": position}
        )
        assert added.json() == {"count": 1}
    assert item_ids(admin, album) == ids
    assert (
        admin.get(f"/api/albums/{album}")
        .json()["cover"]["url"]
        .startswith(f"/api/assets/{b}/thumb")
    ), "the chosen cover comes back with its photo"


def test_positions_count_the_photos_you_see_so_an_undo_never_reorders_others(
    admin: TestClient, ids: list[int], tmp_path: Path
) -> None:
    a, b, c, _ = ids
    write_photo(tmp_path / "hidden" / "h.jpg", seed=77)
    hidden_source = import_folder(admin, tmp_path / "hidden", "hidden")
    h = asset_id_of(admin, hidden_source, "h.jpg")
    assert admin.patch(f"/api/assets/{h}/state", json={"private": True}).is_success
    lea = add_user(admin, "lea")
    album = admin.post("/api/albums", json={"title": "T", "asset_ids": [a, h, b, c]}).json()["id"]
    lea_id = user_id_of(admin, "lea")
    admin.put(f"/api/albums/{album}/members", json=[{"user_id": lea_id, "role": "editor"}])
    assert item_ids(lea, album) == [a, b, c], "lea doesn't see h"

    lea.request("DELETE", f"/api/albums/{album}/items", json={"asset_ids": [b]})
    lea.post(f"/api/albums/{album}/items", json={"asset_ids": [b], "position": 1})

    assert item_ids(lea, album) == [a, b, c]
    assert item_ids(admin, album) == [a, h, b, c], "the hidden photo kept its place"


# --- v1.3: the ZIP is named after what it holds ------------------------------------------------


def _disposition(response: object) -> str:
    return response.headers["content-disposition"]  # type: ignore[attr-defined, no-any-return]


def test_the_zip_is_named_after_its_album_filters_or_count(
    admin: TestClient, ids: list[int]
) -> None:
    album = admin.post(
        "/api/albums", json={"title": 'Été à "Paris" / 2019', "asset_ids": [ids[0]]}
    ).json()["id"]
    by_album = _disposition(admin.post("/api/downloads", json={"album_id": album}))
    assert by_album == (
        'attachment; filename="Ete a _Paris_ _ 2019.zip"; '
        "filename*=UTF-8''%C3%89t%C3%A9%20%C3%A0%20_Paris_%20_%202019.zip"
    )
    by_filter = admin.post("/api/downloads", json={"filters": {"year": 2019, "place": "Paris"}})
    assert 'filename="photos-2019-paris.zip"' in _disposition(by_filter)
    by_ids = admin.post("/api/downloads", json={"ids": [*ids[:3], ids[0]]})
    assert "filename*=UTF-8''photos-3.zip" in _disposition(by_ids)
    form = admin.post(
        "/api/downloads",
        data={"request": '{"filters": {}}'},
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    assert 'filename="photos-all.zip"' in _disposition(form)
