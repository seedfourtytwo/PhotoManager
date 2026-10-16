"""Timeline filters, facets, calendar, map, places, groups, per-user state, date fixes, trash."""

import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.domain.faces import BoundingBox, Face
from tests.api.conftest import (
    BASE,
    PIN,
    add_user,
    asset_id_of,
    import_folder,
    make_settings,
    services_of,
)
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


def _build_lib(admin: TestClient, folder: Path) -> Lib:
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


@pytest.fixture
def lib(admin: TestClient, tmp_path: Path) -> Lib:
    """A fresh library for tests that change it."""
    return _build_lib(admin, tmp_path / "photos")


@pytest.fixture(scope="module")
def shared_lib(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Lib]:
    """One library for the read-only tests (built once per module: imports are the slow part).
    Tests taking it must not change it."""
    root = tmp_path_factory.mktemp("shared")
    with TestClient(create_app(make_settings(root / "data")), base_url=BASE) as admin:
        setup = {"username": "admin", "display_name": "C", "pin": PIN}
        assert admin.post("/api/setup", json=setup).status_code == 201
        yield _build_lib(admin, root / "photos")


def listed(client: TestClient, **params: Any) -> list[int]:
    response = client.get("/api/assets", params={"limit": 500, **params})
    assert response.status_code == 200, response.text
    return [a["id"] for a in response.json()["items"]]


def test_filters_narrow_the_timeline(shared_lib: Lib) -> None:
    c, ids = shared_lib.admin, shared_lib.ids
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
    assert listed(c, source_id=shared_lib.source) == listed(c)
    assert listed(c, source_id=999) == []
    assert c.get("/api/assets", params={"month": 7}).status_code == 400


def test_places_are_geocoded_offline_and_filterable(shared_lib: Lib) -> None:
    c, ids = shared_lib.admin, shared_lib.ids
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


def test_cursor_pagination_works_with_filters(shared_lib: Lib) -> None:
    c, seen, cursor = shared_lib.admin, [], None
    while True:
        params: dict[str, str | int] = {"limit": 1, "has_location": "true"}
        if cursor:
            params["cursor"] = cursor
        page = c.get("/api/assets", params=params).json()
        seen += [a["id"] for a in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == listed(c, has_location="true")


def test_facets_calendar_and_map(shared_lib: Lib) -> None:
    c, ids = shared_lib.admin, shared_lib.ids
    facets = c.get("/api/assets/facets").json()
    assert facets["total"] == 5 and facets["guessed_dates"] == 1
    assert facets["years"] == [
        {"year": 2022, "count": 1},
        {"year": 2021, "count": 1},
        {"year": 2019, "count": 3},
    ]
    assert facets["sources"] == [{"id": shared_lib.source, "label": "photos", "count": 5}]
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


def test_places_list_countries_and_cities_with_cover_and_centre(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    places = c.get("/api/places").json()
    assert [(p["name"], p["kind"], p["country"], p["count"]) for p in places] == [
        ("France", "country", "France", 3),
        ("Paris", "city", "France", 2),
        ("Quimper", "city", "France", 1),
    ]
    france, paris, _ = places
    assert france["cover"] == {
        "asset_id": ids["quimper"],
        "url": f"/api/assets/{ids['quimper']}/thumb?v=0",
        "width": 120,
        "height": 80,
    }, "the newest photo of the place"
    assert paris["cover"]["asset_id"] == ids["paris2"]
    assert (paris["lat"], paris["lon"]) == pytest.approx(PARIS)
    expected = ((2 * PARIS[0] + QUIMPER[0]) / 3, (2 * PARIS[1] + QUIMPER[1]) / 3)
    assert (france["lat"], france["lon"]) == pytest.approx(expected, abs=0.01)
    c.patch(f"/api/assets/{ids['quimper']}/state", json={"hidden": True})
    after = c.get("/api/places").json()
    assert [(p["name"], p["count"]) for p in after] == [("France", 2), ("Paris", 2)], "as facets"
    assert after[0]["cover"]["asset_id"] == ids["paris2"]


def test_every_imported_photo_has_its_dominant_colour(shared_lib: Lib) -> None:
    c, ids = shared_lib.admin, shared_lib.ids
    items = c.get("/api/assets").json()["items"]
    assert len(items) == len(ids)
    assert all(re.fullmatch(r"#[0-9a-f]{6}", a["colour"]) for a in items), items
    colour = next(a["colour"] for a in items if a["id"] == ids["paris1"])
    assert c.get(f"/api/assets/{ids['paris1']}").json()["colour"] == colour


def test_bursts_share_a_group(shared_lib: Lib) -> None:
    c, ids = shared_lib.admin, shared_lib.ids
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


def test_pinned_photos_are_per_user_and_set_like_favourites(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    lea = add_user(c, "lea")
    r = c.patch(f"/api/assets/{ids['paris1']}/state", json={"pinned": True})
    assert r.json()["pinned"] is True and r.json()["favourite"] is False
    bulk = c.post(
        "/api/assets/state", json={"ids": [ids["winter"], ids["quimper"], 999], "pinned": True}
    )
    assert bulk.json() == {"updated": 2}
    assert listed(c, pinned="true") == [ids["winter"], ids["quimper"], ids["paris1"]]
    assert listed(lea, pinned="true") == [], "pinned photos are mine alone"
    assert ids["winter"] in listed(c), "pinning takes nothing off the timeline"
    unpinned = c.patch(f"/api/assets/{ids['paris1']}/state", json={"pinned": False}).json()
    assert unpinned["pinned"] is False
    assert c.get(f"/api/assets/{ids['winter']}").json()["pinned"] is True
    assert set(listed(c, pinned="false")) == {ids["paris1"], ids["paris2"], ids["nodate"]}


def _faces(lib: Lib) -> dict[str, int]:
    """One person on paris1, another on quimper and winter."""
    store = services_of(lib.admin).ml.store

    def face(name: str) -> int:
        found = Face(BoundingBox(0.1, 0.1, 0.3, 0.3), 0.9, (), (1.0, 0.0, 0.0, 0.0))
        (face_id,) = store.replace_faces(lib.ids[name], "f", [found])
        return face_id

    sam = store.create_person(face("paris1"))
    lou = store.create_person(face("quimper"))
    store.assign_face(face("winter"), lou)
    return {"sam": sam, "lou": lou}


def test_person_id_narrows_every_filtered_route(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    who = _faces(lib)
    assert listed(c, person_id=who["sam"]) == [ids["paris1"]]
    assert listed(c, person_id=[who["sam"], who["lou"]]) == [
        ids["winter"],
        ids["quimper"],
        ids["paris1"],
    ]
    lou = {"person_id": who["lou"]}
    assert c.get("/api/assets/facets", params=lou).json()["total"] == 2
    days = c.get("/api/calendar", params=lou).json()
    assert [d["day"] for d in days] == ["2019-08-01", "2021-01-15"]
    assert [p["id"] for p in c.get("/api/map", params=lou).json()] == [ids["quimper"]]
    scope = {"filters": {"person_id": [who["lou"]]}}
    assert c.post("/api/downloads/estimate", json=scope).json()["count"] == 2
    zipped = c.post("/api/downloads", json=scope)
    assert "photos-1-person.zip" in zipped.headers["content-disposition"]
    assert c.get("/api/assets", params={"person_id": 0}).status_code == 400
    no_one = {"filters": {"person_id": [0]}}
    assert c.post("/api/downloads/estimate", json=no_one).status_code == 422


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
    history = services_of(c).db.writer.execute(
        "SELECT old_date_source, new_taken_at FROM date_change WHERE asset_id = ? ORDER BY id",
        (ids["nodate"],),
    )
    assert tuple(history.fetchall()[0]) == ("file_mtime", "2015-06-01T10:00:00")
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


# --- QA A11: out-of-range input is a 4xx, never a 500 -----------------------------------------

HUGE = 2**63  # one past SQLite's largest integer


def test_ids_beyond_sqlite_integers_are_not_found_or_unprocessable(shared_lib: Lib) -> None:
    c = shared_lib.admin
    for path in (
        f"/api/assets/{HUGE}",
        f"/api/assets/{HUGE * 4}/thumb",
        f"/api/albums/{HUGE}",
        f"/api/groups/{HUGE}",
        f"/api/people/{HUGE}",
    ):
        assert c.get(path).status_code == 404, path
    for method, path, body in (
        ("POST", "/api/assets/state", {"ids": [HUGE], "favourite": True}),
        ("DELETE", "/api/assets", {"ids": [HUGE]}),
        ("POST", "/api/trash/restore", {"ids": [HUGE]}),
        ("POST", "/api/albums", {"title": "x", "asset_ids": [HUGE]}),
        ("POST", "/api/downloads/estimate", {"ids": [HUGE]}),
    ):
        assert c.request(method, path, json=body).status_code == 422, path
    assert c.get("/api/assets", params={"source_id": HUGE}).status_code == 400


def test_the_last_day_of_the_calendar_is_a_valid_upper_bound(shared_lib: Lib) -> None:
    c = shared_lib.admin
    everything = listed(c)
    assert listed(c, **{"to": "9999-12-31"}) == everything
    assert c.get("/api/calendar", params={"to": "9999-12-31"}).status_code == 200
    assert c.get("/api/assets/facets", params={"to": "9999-12-31"}).status_code == 200


def test_dates_cannot_be_set_or_shifted_into_the_future(lib: Lib) -> None:
    c, ids = lib.admin, lib.ids
    soon = datetime.now().replace(microsecond=0)
    for body in (
        {"ids": [ids["winter"]], "set": f"{soon.year + 1}-01-01T00:00:00"},
        {"ids": [ids["winter"]], "shift_minutes": 60 * 24 * 365 * 50},
    ):
        refused = c.post("/api/assets/dates", json=body)
        assert refused.status_code == 422, body
        assert "future" in refused.json()["detail"]
    ok = c.post("/api/assets/dates", json={"ids": [ids["winter"]], "set": soon.isoformat()})
    assert ok.json() == {"updated": 1}, "now (up to a day ahead, for time zones) is fine"


def test_the_original_is_named_after_the_file_never_a_path(lib: Lib) -> None:
    """QA A12: a backslash in a (Linux) file name must not reach Content-Disposition."""
    write_photo(lib.folder / "holiday\\..\\evil.jpg", seed=99)
    assert lib.admin.post(f"/api/sources/{lib.source}/scan").status_code == 202
    services_of(lib.admin).worker.run_until_idle()
    asset_id = asset_id_of(lib.admin, lib.source, "holiday\\..\\evil.jpg")
    disposition = lib.admin.get(f"/api/assets/{asset_id}/original").headers["content-disposition"]
    assert 'filename="evil.jpg"' in disposition or "filename*=utf-8''evil.jpg" in disposition


def test_a_missing_thumbnail_size_is_measured_and_stored_on_first_serve(lib: Lib) -> None:
    """QA A12: photos migrated from M1 have no thumb_w/thumb_h."""
    repo = services_of(lib.admin).repo
    asset_id = lib.ids["paris1"]
    repo._write("UPDATE asset SET thumb_w = NULL, thumb_h = NULL WHERE id = ?", (asset_id,))
    asset = repo.get_asset(asset_id)
    assert asset is not None and asset.thumb_size is None
    assert lib.admin.get(f"/api/assets/{asset_id}/thumb").status_code == 200
    measured = repo.get_asset(asset_id)
    assert measured is not None and measured.thumb_size == (120, 80)


def test_changing_dates_or_the_trash_queues_a_full_regroup(lib: Lib) -> None:
    """C29: new photos regroup only their stretch of time; moved or removed ones need it all."""
    c, ids = lib.admin, lib.ids
    repo = services_of(c).repo

    def full_regroups() -> int:
        return sum(1 for j in repo.list_jobs("queued") if j["kind"] == "group" and j["payload"])

    c.post("/api/assets/dates", json={"ids": [ids["winter"]], "shift_minutes": 60})
    assert full_regroups() == 1
    c.request("DELETE", "/api/assets", json={"ids": [ids["paris1"]]})
    c.post("/api/trash/restore", json={"ids": [ids["paris1"]]})
    assert full_regroups() == 1, "one is enough while it waits"
    services_of(c).worker.run_until_idle()
    groups = {a["id"]: a["group_id"] for a in c.get("/api/assets").json()["items"]}
    assert groups[ids["paris1"]] == groups[ids["paris2"]] is not None
