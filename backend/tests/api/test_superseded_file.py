"""A file whose content changed at the same path (a cut-off download in staging later
replaced by the whole file): what becomes of the photo imported from the first version.

A photo is visible through its sources. The path's row goes to the new photo, so the old one
used to be left without any origin: gone for every member, still in every admin's timeline,
never cleaned up. Now it goes to the trash (restorable for 30 days) and the report says so."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, asset_id_of, services_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

KEPT_IN_TRASH = "file changed since the last import; previous version kept in the trash for 30 days"


def _rescan(admin: TestClient, source_id: int) -> list[dict[str, object]]:
    """Scan the source again and answer the files of that run's report."""
    assert admin.post(f"/api/sources/{source_id}/scan").status_code == 202
    services_of(admin).worker.run_until_idle()
    (run, *_) = admin.get("/api/imports", params={"source_id": source_id}).json()
    items: list[dict[str, object]] = admin.get(f"/api/imports/{run['id']}").json()["items"]
    return items


def _source(admin: TestClient, folder: Path, label: str = "Cloud") -> int:
    folder.mkdir(exist_ok=True)
    created = admin.post("/api/sources", json={"label": label, "path": str(folder)})
    assert created.status_code == 201, created.text
    source_id: int = created.json()["id"]
    return source_id


def _ids(client: TestClient, path: str = "/api/assets") -> list[int]:
    body = client.get(path).json()
    return [a["id"] for a in (body["items"] if isinstance(body, dict) else body)]


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    return tmp_path / "staging"


def test_the_first_version_goes_to_the_trash_and_the_report_says_so(
    admin: TestClient, staging: Path
) -> None:
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    _rescan(admin, source_id)
    old = asset_id_of(admin, source_id, "p.jpg")
    lea = add_user(admin, "lea")
    assert _ids(admin) == [old] and _ids(lea) == [old]

    write_photo(staging / "p.jpg", seed=2)
    (item,) = _rescan(admin, source_id)

    new = asset_id_of(admin, source_id, "p.jpg")
    assert new != old
    assert item == {
        "relative_path": "p.jpg",
        "outcome": "imported",
        "reason": KEPT_IN_TRASH,
        "asset_id": new,
    }
    assert _ids(admin) == [new] and _ids(lea) == [new], "nobody's timeline keeps the old one"
    assert _ids(admin, "/api/trash") == [old], "an admin finds it in the trash"
    assert admin.get("/api/stats").json()["assets"] == 1


def test_the_first_version_can_be_restored_and_its_file_is_still_there(
    admin: TestClient, staging: Path
) -> None:
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    _rescan(admin, source_id)
    old = asset_id_of(admin, source_id, "p.jpg")
    write_photo(staging / "p.jpg", seed=2)
    _rescan(admin, source_id)
    services = services_of(admin)
    asset = services.repo.get_asset(old)
    assert asset is not None and services.store.absolute(asset.library_path).is_file()

    assert admin.post("/api/trash/restore", json={"ids": [old]}).status_code == 200

    assert old in _ids(admin) and admin.get(f"/api/assets/{old}").status_code == 200


def test_a_first_version_that_another_file_still_holds_stays_where_it_is(
    admin: TestClient, staging: Path
) -> None:
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    write_photo(staging / "copy of p.jpg", seed=1)
    _rescan(admin, source_id)
    old = asset_id_of(admin, source_id, "copy of p.jpg")

    write_photo(staging / "p.jpg", seed=2)
    items = _rescan(admin, source_id)

    changed = next(i for i in items if i["relative_path"] == "p.jpg")
    assert changed["reason"] == "file changed since the last import; previous version kept"
    assert old in _ids(admin) and _ids(admin, "/api/trash") == []


def test_a_file_changed_back_brings_its_photo_out_of_the_trash(
    admin: TestClient, staging: Path
) -> None:
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    _rescan(admin, source_id)
    first = asset_id_of(admin, source_id, "p.jpg")
    write_photo(staging / "p.jpg", seed=2)
    _rescan(admin, source_id)
    second = asset_id_of(admin, source_id, "p.jpg")

    write_photo(staging / "p.jpg", seed=1)
    (item,) = _rescan(admin, source_id)

    assert asset_id_of(admin, source_id, "p.jpg") == first
    assert _ids(admin) == [first], "the photo the file shows now is the one in the timeline"
    assert _ids(admin, "/api/trash") == [second]
    assert (item["outcome"], item["asset_id"]) == ("duplicate", first)
    assert str(item["reason"]).endswith(KEPT_IN_TRASH)


def test_a_photo_someone_put_in_the_trash_stays_there_when_its_file_is_seen_again(
    admin: TestClient, staging: Path
) -> None:
    """Only what the import itself moved to the trash comes back by itself."""
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    _rescan(admin, source_id)
    mine = asset_id_of(admin, source_id, "p.jpg")
    assert admin.request("DELETE", "/api/assets", json={"ids": [mine]}).status_code == 200

    write_photo(staging / "other name.jpg", seed=1)
    _rescan(admin, source_id)

    assert _ids(admin) == [] and _ids(admin, "/api/trash") == [mine]


def test_a_superseded_photo_purged_after_30_days_may_be_imported_again(
    admin: TestClient, staging: Path
) -> None:
    """Nobody decided its content must stay out: only a person's delete is remembered."""
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    _rescan(admin, source_id)
    write_photo(staging / "p.jpg", seed=2)
    _rescan(admin, source_id)
    services = services_of(admin)
    services.repo._conn.execute(
        "UPDATE asset SET trashed_at = ? WHERE trashed_at IS NOT NULL",
        ((services.clock.now() - timedelta(days=31)).isoformat(),),
    )
    assert services.trash.purge_expired({}) == 1
    assert _ids(admin, "/api/trash") == []

    write_photo(staging / "p.jpg", seed=1)
    (item,) = _rescan(admin, source_id)

    assert item["outcome"] == "imported", item
    assert len(_ids(admin)) == 1


def test_a_photo_a_person_deleted_for_good_still_stays_out(
    admin: TestClient, staging: Path
) -> None:
    source_id = _source(admin, staging)
    write_photo(staging / "p.jpg", seed=1)
    _rescan(admin, source_id)
    mine = asset_id_of(admin, source_id, "p.jpg")
    assert admin.request("DELETE", "/api/assets", json={"ids": [mine]}).status_code == 200
    assert admin.post("/api/trash/empty", json={"ids": [mine]}).status_code == 200

    write_photo(staging / "again.jpg", seed=1)
    items = _rescan(admin, source_id)

    assert {i["outcome"] for i in items} == {"skipped"}
