"""DELETE /api/sources/{id}: stop watching a folder (admin), with its photos kept or trashed.

The folder on disk is an original: removing its source never reads-writes, moves or deletes
anything in it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.services import watched_roots
from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.domain.access import INBOX_KIND, SourceAccess
from tests.api.conftest import (
    add_user,
    asset_id_of,
    import_folder,
    refusal,
    services_of,
    user_id_of,
)
from tests.conftest import snapshot_tree
from tests.factories import NOW
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


def _ids(client: TestClient, path: str = "/api/assets") -> set[int]:
    body = client.get(path).json()
    return {a["id"] for a in (body["items"] if isinstance(body, dict) else body)}


@pytest.fixture
def two_folders(admin: TestClient, tmp_path: Path) -> tuple[int, int, int, int]:
    """Old disk holds a.jpg (only there) and both.jpg (also on the laptop): their ids."""
    old, laptop = tmp_path / "old", tmp_path / "laptop"
    old.mkdir()
    laptop.mkdir()
    write_photo(old / "a.jpg", seed=1)
    write_photo(old / "both.jpg", seed=2)
    write_photo(laptop / "both.jpg", seed=2)
    old_id = import_folder(admin, old, "Old disk")
    laptop_id = import_folder(admin, laptop, "Laptop")
    only = asset_id_of(admin, old_id, "a.jpg")
    shared = asset_id_of(admin, laptop_id, "both.jpg")
    return old_id, laptop_id, only, shared


def test_the_preview_says_how_many_photos_are_found_only_there(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, laptop_id, _, _ = two_folders
    assert admin.get(f"/api/sources/{old_id}/removal").json() == {"photos": 2, "only_here": 1}
    assert admin.get(f"/api/sources/{laptop_id}/removal").json() == {"photos": 1, "only_here": 0}


def _source(client: TestClient, source_id: int) -> dict[str, object] | None:
    return next((s for s in client.get("/api/sources").json() if s["id"] == source_id), None)


def _level(client: TestClient, asset_id: int) -> object:
    return client.get(f"/api/assets/{asset_id}").json()["level"]


def test_keep_everyone_who_sees_the_photos_still_does_at_the_same_level(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, only, shared = two_folders
    lea = add_user(admin, "lea")
    levels = (_level(lea, only), _level(lea, shared))

    response = admin.delete(f"/api/sources/{old_id}")

    assert response.status_code == 200, response.text
    assert response.json() == {"only_here": 1, "trashed": 0, "detached": True}
    assert _ids(admin) == {only, shared} and _ids(lea) == {only, shared}
    assert (_level(lea, only), _level(lea, shared)) == levels
    assert _ids(admin, "/api/trash") == set()


def test_a_kept_source_is_no_longer_watched_and_shows_no_folder(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, _, _ = two_folders
    admin.patch(f"/api/sources/{old_id}", json={"recheck": "daily"})
    admin.delete(f"/api/sources/{old_id}", params={"photos": "keep"})
    kept = _source(admin, old_id)
    assert kept is not None
    assert {k: kept[k] for k in ("kind", "label", "path", "enabled", "recheck", "problem")} == {
        "kind": "kept",
        "label": "Old disk",
        "path": None,
        "enabled": False,
        "recheck": "off",
        "problem": None,
    }
    assert kept["next_check_at"] is None and kept["asset_count"] == 2


def test_a_kept_source_is_never_checked_again(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, laptop_id, _, _ = two_folders
    admin.delete(f"/api/sources/{old_id}")
    unwatched = "this folder is no longer watched; add it again to watch it"
    assert refusal(admin.post(f"/api/sources/{old_id}/scan")) == (422, {"detail": unwatched})
    assert admin.post(f"/api/remote-sources/{old_id}/pull").status_code == 404
    for change in ({"enabled": True}, {"recheck": "hourly"}):
        assert refusal(admin.patch(f"/api/sources/{old_id}", json=change)) == (
            422,
            {"detail": unwatched},
        )
    assert [q["source_id"] for q in admin.post("/api/sources/scan-all").json()] == [laptop_id]
    assert services_of(admin).rechecks.queue_due() == []
    services = services_of(admin)
    services.repo.enqueue(SCAN_JOB_KIND, {"source_id": old_id})  # e.g. queued by an old client
    services.worker.run_until_idle()
    (job,) = [j for j in services.repo.list_jobs("failed") if j["payload"] == {"source_id": old_id}]
    assert "no longer watched" in str(job["error"])


def test_a_kept_sources_label_and_access_can_still_be_changed(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, only, _ = two_folders
    lea = add_user(admin, "lea")
    admin.delete(f"/api/sources/{old_id}")
    assert (
        admin.patch(f"/api/sources/{old_id}", json={"label": "Old disk (2019)"}).status_code == 200
    )
    put = admin.put(f"/api/sources/{old_id}/access", json={"everyone": None, "users": []})
    assert put.status_code == 200
    assert only not in _ids(lea)


def test_a_kept_folder_is_no_source_root_for_the_backup_overlap_check(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, _, _ = two_folders
    admin.delete(f"/api/sources/{old_id}")
    roots = watched_roots(services_of(admin).repo)
    assert old_id not in [
        s.id for s in services_of(admin).repo.list_sources() if Path(s.root) in roots
    ]
    assert all(not str(root).startswith("kept:") for root in roots) and len(roots) == 1


def test_removing_a_kept_source_for_good_leaves_its_only_photos_to_admins(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, only, shared = two_folders
    lea = add_user(admin, "lea")
    admin.delete(f"/api/sources/{old_id}")
    assert admin.get(f"/api/sources/{old_id}/removal").json() == {"photos": 2, "only_here": 1}

    response = admin.delete(f"/api/sources/{old_id}", params={"photos": "keep"})

    assert response.json() == {"only_here": 1, "trashed": 0, "detached": False}
    assert _source(admin, old_id) is None
    assert _ids(admin) == {only, shared}
    assert _ids(lea) == {shared}, "a member reached it only through that folder"


def test_trash_moves_the_photos_found_only_there_to_the_trash_restorable(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, only, shared = two_folders
    lea = add_user(admin, "lea")

    response = admin.delete(f"/api/sources/{old_id}", params={"photos": "trash"})

    assert response.json() == {"only_here": 1, "trashed": 1, "detached": False}
    assert _source(admin, old_id) is None
    assert _ids(admin) == {shared} and _ids(lea) == {shared}
    assert _ids(admin, "/api/trash") == {only}
    row = services_of(admin).repo._one("SELECT trashed_by FROM asset WHERE id = ?", (only,))
    assert row is not None and row["trashed_by"] == user_id_of(admin, "admin")
    assert admin.post("/api/trash/restore", json={"ids": [only]}).json() == {"restored": 1}
    assert _ids(admin) == {only, shared}


@pytest.mark.parametrize("photos", ["keep", "trash"])
def test_nothing_in_the_folder_on_disk_changes(
    admin: TestClient, source_guard: Path, photos: str
) -> None:
    """Rule #1 (originals are sacred), checked here as well as by the fixture on teardown."""
    before = snapshot_tree(source_guard)
    source_id = import_folder(admin, source_guard, "Fixtures")
    assert admin.delete(f"/api/sources/{source_id}", params={"photos": photos}).status_code == 200
    assert snapshot_tree(source_guard) == before


def test_the_folder_can_be_added_again_and_its_photos_come_back(
    admin: TestClient, two_folders: tuple[int, int, int, int], tmp_path: Path
) -> None:
    old_id, _, only, _ = two_folders
    admin.delete(f"/api/sources/{old_id}", params={"photos": "keep"})
    again = import_folder(admin, tmp_path / "old", "Old disk")
    assert asset_id_of(admin, again, "a.jpg") == only, "the same photo, not a copy"


def test_only_admins_may_remove_a_folder_or_preview_it(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, _, _ = two_folders
    lea = add_user(admin, "lea")
    assert lea.delete(f"/api/sources/{old_id}").status_code == 403
    assert lea.get(f"/api/sources/{old_id}/removal").status_code == 403
    assert old_id in {s["id"] for s in admin.get("/api/sources").json()}


def test_an_unknown_choice_or_source_is_refused(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, _, _ = two_folders
    assert admin.delete(f"/api/sources/{old_id}", params={"photos": "purge"}).status_code == 422
    assert refusal(admin.delete("/api/sources/999")) == (404, {"detail": "source not found"})
    assert admin.get("/api/sources/999/removal").status_code == 404


def test_an_upload_inbox_is_refused(admin: TestClient) -> None:
    repo = services_of(admin).repo
    inbox = repo.add_source(
        "Uploads (C)", "/data/inbox/1", owner_id=1, kind=INBOX_KIND, access=SourceAccess(None)
    )
    assert refusal(admin.delete(f"/api/sources/{inbox.id}")) == (
        422,
        {"detail": "an upload inbox belongs to its account and cannot be removed"},
    )


def test_refused_while_its_check_is_running(
    admin: TestClient, two_folders: tuple[int, int, int, int]
) -> None:
    old_id, _, only, _ = two_folders
    repo = services_of(admin).repo
    repo.enqueue(SCAN_JOB_KIND, {"source_id": old_id})
    assert repo.claim_next_job(NOW) is not None
    status, body = refusal(admin.delete(f"/api/sources/{old_id}", params={"photos": "trash"}))
    assert status == 409 and "being checked" in str(body)
    assert _ids(admin) >= {only}
