"""Album → print over HTTP (docs/contracts/api-v1.md, "Album → print"), with real libvips
renditions and Typst."""

import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.domain.print_layout import BLEED_MM, MM_PER_INCH
from tests.api.conftest import (
    add_user,
    asset_id_of,
    import_folder,
    refusal,
    services_of,
    user_id_of,
)
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

PT_PER_MM = 72 / MM_PER_INCH
BIG = (2400, 1600)


def media_boxes(pdf: bytes) -> list[tuple[float, float]]:
    """(width, height) in mm of every page; Typst writes no object streams."""
    sizes = []
    for box in re.findall(rb"/MediaBox\s*\[\s*([\d.\s-]+)\]", pdf):
        x0, y0, x1, y1 = (float(v) for v in box.split())
        sizes.append((round((x1 - x0) / PT_PER_MM, 1), round((y1 - y0) / PT_PER_MM, 1)))
    return sizes


@pytest.fixture
def album(admin: TestClient, tmp_path: Path) -> dict[str, int]:
    folder = tmp_path / "trip"
    for i in range(4):
        write_photo(folder / f"p{i}.jpg", seed=i, size=BIG, taken=datetime(2024, 7, 1 + i, 10))
    write_photo(folder / "tiny.jpg", seed=9, size=(120, 80), taken=datetime(2024, 7, 9, 10))
    source = import_folder(admin, folder, "Trip")
    ids = {f"p{i}": asset_id_of(admin, source, f"p{i}.jpg") for i in range(4)}
    ids["tiny"] = asset_id_of(admin, source, "tiny.jpg")
    created = admin.post(
        "/api/albums", json={"title": "Summer", "asset_ids": [ids[f"p{i}"] for i in range(4)]}
    )
    ids["album"] = created.json()["id"]
    return ids


REQUEST = {"trim": "a4-landscape", "theme": "quiet", "cover": True}


def test_options_come_from_the_print_engine(admin: TestClient) -> None:
    body = admin.get("/api/print/options").json()
    assert {
        "id": "a4-landscape",
        "label": "A4 landscape",
        "width_mm": 297.0,
        "height_mm": 210.0,
    } in body["trims"]
    assert {t["id"] for t in body["themes"]} == {"quiet", "warm", "night"}
    assert any(lay["id"] == "four-grid" and lay["capacity"] == 4 for lay in body["layouts"])


def test_plan_lists_pages_with_asset_ids(admin: TestClient, album: dict[str, int]) -> None:
    body = admin.post(f"/api/albums/{album['album']}/print/plan", json=REQUEST).json()
    placed = [a for page in body["pages"] for a in page["photos"]]
    assert sorted(placed) == sorted(album[f"p{i}"] for i in range(4))
    assert body["page_count"] == len(body["pages"]) + 1  # the cover
    assert body["issues"] == []


def test_pdf_has_the_trim_plus_bleed_on_every_page(
    admin: TestClient, album: dict[str, int]
) -> None:
    response = admin.post(f"/api/albums/{album['album']}/print", json=REQUEST)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="Summer.pdf"' in response.headers["content-disposition"]
    assert response.headers["x-print-warnings"] == "0"
    plan = admin.post(f"/api/albums/{album['album']}/print/plan", json=REQUEST).json()
    boxes = media_boxes(response.content)
    assert len(boxes) == plan["page_count"]
    assert set(boxes) == {(297 + 2 * BLEED_MM, 210 + 2 * BLEED_MM)}


def test_plans_render_nothing(admin: TestClient, album: dict[str, int]) -> None:
    admin.post(f"/api/albums/{album['album']}/print/plan", json=REQUEST)
    root = services_of(admin).settings.data_root
    assert not (root / "derived" / "print").exists()


def test_print_renditions_are_cached_with_the_edit_applied(
    admin: TestClient, album: dict[str, int]
) -> None:
    p0 = album["p0"]
    edit = {"rotate": 90, "flip_horizontal": False, "flip_vertical": False, "crop": None,
            "straighten": 0}  # fmt: skip
    assert admin.put(f"/api/assets/{p0}/edit", json=edit).status_code == 200
    assert admin.post(f"/api/albums/{album['album']}/print", json=REQUEST).status_code == 200
    root = services_of(admin).settings.data_root
    renditions = sorted((root / "derived" / "print").rglob("*.jpg"))
    assert len(renditions) == 4
    import pyvips  # type: ignore[import-untyped]

    sizes = {(pyvips.Image.new_from_file(str(p)).width, pyvips.Image.new_from_file(str(p)).height)
             for p in renditions}  # fmt: skip
    assert sizes == {BIG, (BIG[1], BIG[0])}, "the rotated photo is printed rotated"
    stamps = [p.stat().st_mtime_ns for p in renditions]
    admin.post(f"/api/albums/{album['album']}/print", json=REQUEST)
    assert [p.stat().st_mtime_ns for p in renditions] == stamps, "made once, then reused"


def test_an_oversized_print_request_is_unprocessable(
    admin: TestClient, album: dict[str, int]
) -> None:
    url = f"/api/albums/{album['album']}/print/plan"
    fine = [{"layout_id": "text", "asset_ids": [], "text": "x" * 5000}]
    assert admin.post(url, json={**REQUEST, "pages": fine}).status_code == 200
    long_text = [{"layout_id": "text", "asset_ids": [], "text": "x" * 5001}]
    assert admin.post(url, json={**REQUEST, "pages": long_text}).status_code == 422
    many = [{"layout_id": "text", "asset_ids": []}] * 10_001
    assert admin.post(url, json={**REQUEST, "pages": many}).status_code == 422


def test_manual_pages_and_bad_layouts(admin: TestClient, album: dict[str, int]) -> None:
    pages = [{"layout_id": "two-side", "asset_ids": [album["p0"], album["p1"]], "text": "Day 1"}]
    body = admin.post(
        f"/api/albums/{album['album']}/print/plan", json={**REQUEST, "pages": pages}
    ).json()
    assert body["pages"] == [
        {"layout_id": "two-side", "photos": [album["p0"], album["p1"]], "text": "Day 1"}
    ]
    wrong = [{"layout_id": "two-side", "asset_ids": [album["p0"]]}]
    assert (
        admin.post(
            f"/api/albums/{album['album']}/print/plan", json={**REQUEST, "pages": wrong}
        ).status_code
        == 422
    )
    unknown = [{"layout_id": "nope", "asset_ids": [album["p0"]]}]
    assert (
        admin.post(
            f"/api/albums/{album['album']}/print/plan", json={**REQUEST, "pages": unknown}
        ).status_code
        == 422
    )
    stranger = [{"layout_id": "single", "asset_ids": [album["tiny"]]}]
    assert (
        admin.post(
            f"/api/albums/{album['album']}/print/plan", json={**REQUEST, "pages": stranger}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            f"/api/albums/{album['album']}/print/plan", json={**REQUEST, "trim": "a0"}
        ).status_code
        == 422
    )


def test_print_refusals_say_why(admin: TestClient, album: dict[str, int]) -> None:
    base = f"/api/albums/{album['album']}/print"

    def planned(**changes: object) -> tuple[int, object]:
        return refusal(admin.post(f"{base}/plan", json={**REQUEST, **changes}))

    wrong = [{"layout_id": "two-side", "asset_ids": [album["p0"]]}]
    assert planned(pages=wrong) == (422, {"detail": "layout 'two-side' holds 2 photo(s), got 1"})
    unknown = [{"layout_id": "nope", "asset_ids": [album["p0"]]}]
    assert planned(pages=unknown) == (422, {"detail": "unknown layout: 'nope'"})
    stranger = [{"layout_id": "single", "asset_ids": [album["tiny"]]}]
    assert planned(pages=stranger) == (
        422,
        {"detail": f"photo {album['tiny']} is not in this album"},
    )
    assert planned(trim="a0") == (422, {"detail": "unknown trim size: 'a0'"})
    assert planned(theme="neon") == (422, {"detail": "unknown theme: 'neon'"})
    assert refusal(admin.post(base, json={**REQUEST, "theme": "neon"})) == (
        422,
        {"detail": "unknown theme: 'neon'"},
    )
    outside = admin.get(f"{base}/preview", params={"page": 99})
    assert refusal(outside) == (422, {"detail": "page 99 is outside 1..2"})

    empty = admin.post("/api/albums", json={"title": "Empty", "asset_ids": []}).json()["id"]
    nothing = admin.post(f"/api/albums/{empty}/print/plan", json={**REQUEST, "cover": False})
    assert refusal(nothing) == (422, {"detail": "the album has no photos and no cover"})


def test_a_blocked_print_names_the_photos_that_are_too_small(
    admin: TestClient, album: dict[str, int]
) -> None:
    admin.post(f"/api/albums/{album['album']}/items", json={"asset_ids": [album["tiny"]]})
    blocked = admin.post(f"/api/albums/{album['album']}/print", json=REQUEST)
    assert blocked.status_code == 422
    body = blocked.json()
    assert body["detail"] == "1 photo(s) are too small to print at this size"
    assert [i["asset_id"] for i in body["issues"]] == [album["tiny"]]


def test_low_resolution_blocks_unless_allowed(admin: TestClient, album: dict[str, int]) -> None:
    admin.post(f"/api/albums/{album['album']}/items", json={"asset_ids": [album["tiny"]]})
    blocked = admin.post(f"/api/albums/{album['album']}/print", json=REQUEST)
    assert blocked.status_code == 422
    issues = blocked.json()["issues"]
    assert [i["asset_id"] for i in issues] == [album["tiny"]] and issues[0]["level"] == "block"
    allowed = admin.post(
        f"/api/albums/{album['album']}/print", json={**REQUEST, "allow_low_resolution": True}
    )
    assert allowed.status_code == 200
    assert allowed.headers["x-print-warnings"] == "1"


def test_preview_renders_one_page_as_png(admin: TestClient, album: dict[str, int]) -> None:
    url = f"/api/albums/{album['album']}/print/preview"
    response = admin.get(url, params={"page": 2, "trim": "a4-landscape", "theme": "warm"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert admin.get(url, params={"page": 0}).status_code == 422
    assert admin.get(url, params={"page": 99}).status_code == 422


def test_printing_needs_download_on_every_photo(admin: TestClient, album: dict[str, int]) -> None:
    lea = add_user(admin, "lea")
    sources = admin.get("/api/sources").json()
    lea_id = user_id_of(admin, "lea")
    admin.put(
        f"/api/sources/{sources[0]['id']}/access",
        json={"everyone": None, "users": [{"user_id": lea_id, "level": "view"}]},
    )
    shared = admin.post("/api/albums", json={"title": "Shared", "asset_ids": [album["p0"]]})
    album_id = shared.json()["id"]
    admin.put(f"/api/albums/{album_id}/members", json=[{"user_id": lea_id, "role": "viewer"}])
    assert lea.post(f"/api/albums/{album_id}/print", json=REQUEST).status_code == 403
    assert lea.post(f"/api/albums/{album_id}/print/plan", json=REQUEST).status_code == 403
    assert lea.get(f"/api/albums/{album_id}/print/preview?page=1").status_code == 403
    assert lea.post(f"/api/albums/{album['album']}/print", json=REQUEST).status_code == 404
    anon = TestClient(admin.app, base_url="http://127.0.0.1")
    assert anon.get("/api/print/options").status_code == 401
