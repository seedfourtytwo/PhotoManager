"""Sources that check themselves again on a timer (issues 7 and 8), through the real app."""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import IntegrationSettings
from photo_assistant.app.recheck import ScheduledChecks
from tests.api.conftest import BASE, PIN, add_user, import_folder, make_settings, services_of

FIXTURES = Path(__file__).parent.parent / "fixtures" / "photos"


class Later:
    """The wall clock, some time from now."""

    def __init__(self, ahead: timedelta) -> None:
        self._ahead = ahead

    def now(self) -> datetime:
        return datetime.now(UTC) + self._ahead


def _source(client: TestClient, source_id: int) -> dict[str, object]:
    found: dict[str, object] = next(
        s for s in client.get("/api/sources").json() if s["id"] == source_id
    )
    return found


def _scan_jobs(client: TestClient, status: str | None = None) -> list[dict[str, object]]:
    jobs = services_of(client).repo.list_jobs(status)
    return [j for j in jobs if j["kind"] == "scan_source"]


def _look(client: TestClient, ahead: timedelta) -> list[int]:
    """What the periodic check would queue if it looked ``ahead`` from now."""
    return ScheduledChecks(services_of(client).repo, Later(ahead)).queue_due()


def _pictures(tmp_path: Path) -> Path:
    folder = tmp_path / "pics"
    folder.mkdir()
    shutil.copy(FIXTURES / "IMG_1002.JPG", folder / "a.jpg")
    return folder


# --- the setting ------------------------------------------------------------------------------


def test_a_source_is_off_until_an_admin_turns_automatic_checks_on(
    admin: TestClient, source_guard: Path
) -> None:
    source_id = import_folder(admin, source_guard, "Pictures")
    assert _source(admin, source_id)["recheck"] == "off"
    assert _source(admin, source_id)["next_check_at"] is None

    patched = admin.patch(f"/api/sources/{source_id}", json={"recheck": "daily"})

    assert patched.status_code == 200
    assert patched.json()["recheck"] == "daily"
    (run,) = admin.get("/api/imports", params={"source_id": source_id}).json()
    expected = datetime.fromisoformat(run["started_at"]) + timedelta(days=1)
    assert datetime.fromisoformat(patched.json()["next_check_at"]) == expected
    assert _source(admin, source_id)["next_check_at"] == patched.json()["next_check_at"]


def test_a_disabled_source_has_no_next_check(admin: TestClient, source_guard: Path) -> None:
    source_id = import_folder(admin, source_guard, "Pictures")
    admin.patch(f"/api/sources/{source_id}", json={"recheck": "hourly"})
    disabled = admin.patch(f"/api/sources/{source_id}", json={"enabled": False}).json()
    assert (disabled["recheck"], disabled["next_check_at"]) == ("hourly", None)
    assert _look(admin, timedelta(days=30)) == []


@pytest.mark.parametrize("value", ["monthly", "", "Daily", 5])
def test_any_other_setting_is_refused(admin: TestClient, source_guard: Path, value: object) -> None:
    created = admin.post("/api/sources", json={"label": "P", "path": str(source_guard)}).json()
    refused = admin.patch(f"/api/sources/{created['id']}", json={"recheck": value})
    assert refused.status_code == 422
    assert _source(admin, created["id"])["recheck"] == "off"


def test_only_an_admin_may_change_the_setting(admin: TestClient, source_guard: Path) -> None:
    created = admin.post("/api/sources", json={"label": "P", "path": str(source_guard)}).json()
    lea = add_user(admin, "lea")
    assert lea.patch(f"/api/sources/{created['id']}", json={"recheck": "daily"}).status_code == 403
    assert _source(admin, created["id"])["recheck"] == "off"


# --- the timer --------------------------------------------------------------------------------


def test_the_server_looks_for_due_sources_every_few_minutes(admin: TestClient) -> None:
    services = services_of(admin)
    assert "due folder checks" in services.ops.periodic.task_names
    assert 60 <= services.settings.source_recheck_poll_seconds <= 600


def test_a_due_source_is_queued_once_however_often_the_server_looks(
    admin: TestClient, source_guard: Path
) -> None:
    created = admin.post("/api/sources", json={"label": "P", "path": str(source_guard)}).json()
    admin.patch(f"/api/sources/{created['id']}", json={"recheck": "weekly"})
    periodic = services_of(admin).ops.periodic

    periodic.tick()  # never checked: due at the first look
    assert _look(admin, timedelta()) == [], "its check is waiting: not queued a second time"

    (job,) = _scan_jobs(admin)
    assert (job["payload"], job["status"]) == ({"source_id": created["id"]}, "queued")


def test_a_scheduled_recheck_of_an_unchanged_folder_adds_no_photos(
    admin: TestClient, source_guard: Path
) -> None:
    """Issue 7's acceptance; ``source_guard`` also proves the folder is left byte-identical."""
    source_id = import_folder(admin, source_guard, "Pictures")
    photos = _source(admin, source_id)["asset_count"]
    admin.patch(f"/api/sources/{source_id}", json={"recheck": "hourly"})

    assert _look(admin, timedelta(minutes=59)) == [], "not an hour yet"
    assert _look(admin, timedelta(minutes=61)) == [source_id]
    services_of(admin).worker.run_until_idle()

    latest, first = admin.get("/api/imports", params={"source_id": source_id}).json()
    assert first["summary"]["imported"] == photos and photos
    assert (latest["status"], latest["summary"]["imported"]) == ("done", 0)
    assert _source(admin, source_id)["asset_count"] == photos
    assert _look(admin, timedelta(minutes=59)) == [], "the hour counts from the new check"


def test_a_check_that_fails_waits_for_the_next_interval(admin: TestClient, tmp_path: Path) -> None:
    folder = _pictures(tmp_path)
    source_id = import_folder(admin, folder, "Stick")
    admin.patch(f"/api/sources/{source_id}", json={"recheck": "hourly"})
    shutil.rmtree(folder)  # the stick was unplugged (a copy made for this test)

    assert _look(admin, timedelta(hours=2)) == [source_id]
    services_of(admin).worker.run_until_idle()

    assert [j["status"] for j in _scan_jobs(admin)] == ["done", "failed"]
    assert _look(admin, timedelta(minutes=30)) == [], "no retry at every look"
    assert _look(admin, timedelta(hours=2)) == [source_id], "tried again an hour later"


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")
def test_a_scheduled_pull_imports_new_files_and_the_next_one_adds_none(tmp_path: Path) -> None:
    """Issue 8's acceptance, with a local folder standing in for the cloud drive."""
    cloud = _pictures(tmp_path)
    config = tmp_path / "rclone.conf"
    config.write_text("[drive]\ntype = local\n")
    settings = make_settings(
        tmp_path / "data", integrations=IntegrationSettings(rclone_config=config)
    )
    with TestClient(create_app(settings), base_url=BASE) as admin:
        admin.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
        added = admin.post(
            "/api/remote-sources", json={"label": "Drive", "remote": "drive", "path": str(cloud)}
        )
        assert added.status_code == 201, added.text
        source_id = added.json()["id"]
        admin.patch(f"/api/sources/{source_id}", json={"recheck": "daily"})

        imported = []
        for day in (0, 2, 4):
            assert _look(admin, timedelta(days=day)) == [source_id]
            services_of(admin).worker.run_until_idle()
            runs = admin.get("/api/imports", params={"source_id": source_id}).json()
            imported.append(runs[0]["summary"]["imported"])
            if day == 0:
                shutil.copy(FIXTURES / "IMG_1004.HEIC", cloud / "b.heic")  # new in the cloud
                (cloud / "a.jpg").unlink()  # and one removed there

        assert imported == [1, 1, 0]
        assert _source(admin, source_id)["asset_count"] == 2, "a remote deletion removes nothing"
