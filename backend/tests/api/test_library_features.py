"""Timeline filters, facets, calendar, map, places, groups, per-user state, date fixes, trash."""

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, asset_id_of, import_folder, services_of
from tests.conftest import snapshot_tree
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

PARIS = (48.8566, 2.3522)
QUIMPER = (47.996, -4.102)


@dataclass
class Lib:
    admin: TestClient
    source: int
    folder: Path
    ids: dict[str, int]


@pytest.fixture
def lib(admin: TestClient, tmp_path: Path) -> Lib:
    folder = tmp_path / "photos"
    specs = {
        "paris1": dict(taken=datetime(2019, 7, 4, 18, 30, 0), gps=PARIS, camera="Pixel 7"),
        "paris2": dict(taken=datetime(2019, 7, 4, 18, 30, 2), gps=PARIS, camera="Pixel 7"),
        "quimper": dict(taken=datetime(2019, 8, 1, 9, 0), gps=QUIMPER, camera="iPhone 12"),
        "winter": dict(taken=datetime(2021, 1, 15, 12, 0), camera="iPhone 12"),
        "nodate": dict(),
    }
    for seed, (name, spec) in enumerate(specs.items()):
        write_photo(folder / f"{name}.jpg", seed=seed * 7, size=(120, 80), **spec)  # type: ignore[arg-type]
    stamp = time.mktime((2022, 3, 3, 10, 0, 0, 0, 0, -1))
    os.utime(folder / "nodate.jpg", (stamp, stamp))
    source = import_folder(admin, folder, "photos")
    ids = {name: asset_id_of(admin, source, f"{name}.jpg") for name in specs}
    return Lib(admin, source, folder, ids)


def listed(client: TestClient, **params: object) -> list[int]:
    response = client.get("/api/assets", params={"limit": 500, **params})
    assert response.status_code == 200, response.text
    return [a["id"] for a in response.json()["items"]]


def test_filters_narrow_the_timeline(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    assert listed(c, year=2019) == [ids["quimper"], ids["paris2"], ids["paris1"]]
    assert listed(c, year=2019, month=7) == [ids["paris2"], ids["paris1"]]
    assert listed(c, **{"from": "2019-08-01", "to": "2021-01-15"}) == [
        ids["winter"],
        ids["quimper"],
    ]
    assert set(listed(c, camera="iPhone 12")) == {ids["quimper"], ids["winter"]}
    assert set(listed(c, has_location="true")) == {ids["paris1"], ids["paris2"], ids["quimper"]}
    assert set(listed(c, has_location="false")) == {ids["winter"], ids["nodate"]}
    assert listed(c, guessed_date="true") == [ids["nodate"]]
    assert listed(c, source_id=lib.source) == listed(c)
    assert listed(c, source_id=999) == []
    assert c.get("/api/assets", params={"month": 7}).status_code == 400


def test_places_are_geocoded_offline_and_filterable(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    detail = c.get(f"/api/assets/{ids['paris1']}").json()
    assert detail["place"] == {"country": "France", "region": "Ile-de-France", "city": "Paris"}
    assert c.get(f"/api/assets/{ids['winter']}").json()["place"] is None
    assert set(listed(c, place="france")) == {ids["paris1"], ids["paris2"], ids["quimper"]}
    assert set(listed(c, place="PARIS")) == {ids["paris1"], ids["paris2"]}
    assert set(listed(c, place="brittany")) == {ids["quimper"]}
    assert set(listed(c, q="paris")) == {ids["paris1"], ids["paris2"]}, "file name or place"
    assert set(listed(c, q="iphone 12")) == {ids["quimper"], ids["winter"]}
    assert listed(c, q="50%") == []


def test_search_finds_album_titles(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    c.post("/api/albums", json={"title": "Summer holidays", "asset_ids": [ids["winter"]]})
    assert listed(c, q="holidays") == [ids["winter"]]


def test_cursor_pagination_works_with_filters(lib: Lib) -> None:
    c, seen, cursor = lib.admin, [], None
    while True:
        params: dict[str, object] = {"limit": 1, "has_location": "true"}
        if cursor:
            params["cursor"] = cursor
        page = c.get("/api/assets", params=params).json()
        seen += [a["id"] for a in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == listed(c, has_location="true")


def test_facets_calendar_and_map(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    facets = c.get("/api/assets/facets").json()
    assert facets["total"] == 5 and facets["guessed_dates"] == 1
    assert facets["years"] == [
        {"year": 2022, "count": 1},
        {"year": 2021, "count": 1},
        {"year": 2019, "count": 3},
    ]
    assert facets["sources"] == [{"id": lib.source, "label": "photos", "count": 5}]
    assert {"name": "iPhone 12", "count": 2} in facets["cameras"]
    assert {"name": "France", "count": 3} in facets["places"]
    assert {"name": "Paris", "count": 2} in facets["places"]
    filtered = c.get("/api/assets/facets", params={"camera": "Pixel 7"}).json()
    assert filtered["total"] == 2
    days = c.get("/api/calendar", params={"year": 2019}).json()
    assert days == [{"day": "2019-07-04", "count": 2}, {"day": "2019-08-01", "count": 1}]
    points = c.get("/api/map").json()
    assert {p["id"] for p in points} == {ids["paris1"], ids["paris2"], ids["quimper"]}
    assert abs(points[0]["lat"]) > 0


def test_bursts_share_a_group(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    first = c.get(f"/api/assets/{ids['paris1']}").json()
    assert first["group_id"] == min(ids["paris1"], ids["paris2"])
    assert c.get(f"/api/assets/{ids['winter']}").json()["group_id"] is None
    members = c.get(f"/api/groups/{first['group_id']}").json()
    assert [m["id"] for m in members] == [ids["paris1"], ids["paris2"]]
    assert c.get("/api/groups/99999").status_code == 404


def test_favourites_and_hidden_are_per_user(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    lea = add_user(c, "lea")
    r = c.patch(f"/api/assets/{ids['paris1']}/state", json={"favourite": True})
    assert r.json()["favourite"] is True and r.json()["hidden"] is False
    assert listed(c, favourite="true") == [ids["paris1"]]
    assert listed(lea, favourite="true") == [], "favourites are mine alone"
    bulk = c.post(
        "/api/assets/state", json={"ids": [ids["winter"], ids["quimper"], 999], "hidden": True}
    )
    assert bulk.json() == {"updated": 2}
    assert ids["winter"] not in listed(c), "hidden photos leave the timeline"
    assert set(listed(c, hidden="true")) == {ids["winter"], ids["quimper"]}
    assert ids["winter"] in listed(lea)
    assert c.get(f"/api/assets/{ids['winter']}").json()["hidden"] is True


def test_fix_dates_set_and_shift_keep_history(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    r = c.post("/api/assets/dates", json={"ids": [ids["nodate"]], "set": "2015-06-01T10:00:00"})
    assert r.json() == {"updated": 1}
    fixed = c.get(f"/api/assets/{ids['nodate']}").json()
    assert fixed["taken_at"] == "2015-06-01T10:00:00" and fixed["date_source"] == "manual"
    assert listed(c, guessed_date="true") == []
    shift = c.post(
        "/api/assets/dates", json={"ids": [ids["paris1"], ids["paris2"]], "shift_minutes": -120}
    )
    assert shift.json() == {"updated": 2}
    assert c.get(f"/api/assets/{ids['paris1']}").json()["taken_at"] == "2019-07-04T16:30:00"
    history = services_of(c).repo.date_history(ids["nodate"])
    assert history[0][1] == "file_mtime" and history[0][2] == datetime(2015, 6, 1, 10)
    both = c.post(
        "/api/assets/dates",
        json={"ids": [ids["winter"]], "set": "2015-06-01T10:00:00", "shift_minutes": 5},
    )
    assert both.status_code == 422
    early = c.post("/api/assets/dates", json={"ids": [ids["winter"]], "set": "1700-01-01T00:00:00"})
    assert early.status_code == 422
    lea = add_user(c, "lea")
    assert (
        lea.post("/api/assets/dates", json={"ids": [ids["winter"]], "shift_minutes": 5}).status_code
        == 403
    )
    assert c.post("/api/assets/dates", json={"ids": [999], "shift_minutes": 5}).status_code == 404


def test_trash_restore_and_purge_never_touch_the_source(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    before = snapshot_tree(lib.folder)
    lea = add_user(c, "lea")
    denied = lea.request("DELETE", "/api/assets", json={"ids": [ids["winter"]]})
    assert denied.status_code == 403, "download access is not enough to delete"
    r = c.request("DELETE", "/api/assets", json={"ids": [ids["winter"], ids["nodate"]]})
    assert r.json() == {"trashed": 2}
    assert ids["winter"] not in listed(c) and ids["winter"] not in listed(lea)
    assert c.get(f"/api/assets/{ids['winter']}").status_code == 404
    trash = c.get("/api/trash").json()
    assert {t["id"] for t in trash} == {ids["winter"], ids["nodate"]}
    assert all(t["trashed_at"] for t in trash)
    assert c.post("/api/trash/restore", json={"ids": [ids["nodate"]]}).json() == {"restored": 1}
    assert ids["nodate"] in listed(c)
    assert lea.post("/api/trash/empty", json={}).status_code == 403
    library_file = services_of(c).store.absolute(
        services_of(c).repo.get_asset(ids["winter"]).library_path  # type: ignore[union-attr]
    )
    assert c.post("/api/trash/empty", json={}).json() == {"purged": 1}
    assert not library_file.exists()
    assert c.get("/api/trash").json() == []
    assert snapshot_tree(lib.folder) == before, "sources are never touched"
    # a rescan does not bring the purged photo back
    assert c.post(f"/api/sources/{lib.source}/scan").status_code == 202
    services_of(c).worker.run_until_idle()
    runs = c.get("/api/imports", params={"source_id": lib.source}).json()
    report = c.get(f"/api/imports/{runs[0]['id']}", params={"outcome": "skipped"}).json()
    assert report["items"] == [
        {
            "relative_path": "winter.jpg",
            "outcome": "skipped",
            "reason": "deleted from the library earlier",
            "asset_id": None,
        }
    ]
    assert ids["winter"] not in listed(c) and len(listed(c)) == 4


def test_trash_empty_with_ids_and_without_body(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    c.request("DELETE", "/api/assets", json={"ids": [ids["winter"], ids["nodate"]]})
    assert c.post("/api/trash/empty", json={"ids": [ids["nodate"]]}).json() == {"purged": 1}
    assert c.post("/api/trash/empty").json() == {"purged": 1}
