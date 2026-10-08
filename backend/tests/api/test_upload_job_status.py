"""After an upload, the uploader may ask how the import of their own upload is doing.

``/api/jobs`` is admin-only, so a member's browser used to wait for the whole queue to be
empty (always its full minute during a big import). This answers one job, and only the import
of the caller's own inbox: any other job is "not found", whoever asks."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import BASE, add_user, refusal, services_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

NOT_YOURS = (404, {"detail": "no import of an upload of yours with that id"})


def _upload(client: TestClient, photo: Path, **extra: object) -> int:
    with photo.open("rb") as handle:
        files = {"file": (photo.name, handle, "image/jpeg")}
        response = client.post("/api/upload", files=files, **extra)  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    job_id: int = response.json()["import_job_id"]
    return job_id


def test_the_uploader_sees_their_import_go_from_queued_to_done(
    admin: TestClient, tmp_path: Path
) -> None:
    lea = add_user(admin, "lea")
    job_id = _upload(lea, write_photo(tmp_path / "a.jpg", seed=1))

    waiting = lea.get(f"/api/upload/jobs/{job_id}")
    assert waiting.status_code == 200
    assert waiting.json() == {"id": job_id, "status": "queued", "run_after": None}

    services_of(admin).worker.run_until_idle()

    assert lea.get(f"/api/upload/jobs/{job_id}").json() == {
        "id": job_id,
        "status": "done",
        "run_after": None,
    }
    assert len(lea.get("/api/assets").json()["items"]) == 1


def test_nobody_else_learns_of_that_job_not_even_an_admin(
    admin: TestClient, tmp_path: Path
) -> None:
    lea, tom = add_user(admin, "lea"), add_user(admin, "tom")
    job_id = _upload(lea, write_photo(tmp_path / "a.jpg", seed=1))

    assert refusal(tom.get(f"/api/upload/jobs/{job_id}")) == NOT_YOURS
    assert refusal(admin.get(f"/api/upload/jobs/{job_id}")) == NOT_YOURS
    assert refusal(lea.get("/api/upload/jobs/999")) == NOT_YOURS, "unknown reads the same"


def test_other_jobs_are_not_answered_whoever_asks(admin: TestClient, tmp_path: Path) -> None:
    """A folder's scan, and the previews an import queues, are not "your upload"."""
    write_photo(tmp_path / "pics" / "a.jpg", seed=1)
    created = admin.post("/api/sources", json={"label": "Pics", "path": str(tmp_path / "pics")})
    scan = admin.post(f"/api/sources/{created.json()['id']}/scan").json()["job_id"]
    services_of(admin).worker.run_until_idle()
    jobs = {job["kind"]: job["id"] for job in admin.get("/api/jobs").json()}
    assert {"scan_source", "preview"} <= set(jobs)

    for job_id in (scan, jobs["preview"]):
        assert refusal(admin.get(f"/api/upload/jobs/{job_id}")) == NOT_YOURS


def test_a_failed_import_that_waits_for_its_retry_says_when(
    admin: TestClient, tmp_path: Path
) -> None:
    job_id = _upload(admin, write_photo(tmp_path / "a.jpg", seed=1))
    services = services_of(admin)
    services.repo.claim_next_job(services.clock.now())
    services.repo.fail_job(job_id, "disk hiccup", retry=True, run_after=services.clock.now())

    body = admin.get(f"/api/upload/jobs/{job_id}").json()

    assert body["status"] == "queued" and body["run_after"] is not None
    assert "error" not in body, "the reason is the admin's to read, in /api/jobs"


def test_a_device_token_may_ask_about_its_own_upload(admin: TestClient, tmp_path: Path) -> None:
    token = admin.post("/api/devices", json={"name": "Phone"}).json()["token"]
    phone = TestClient(admin.app, base_url=BASE)
    bearer = {"Authorization": f"Bearer {token}"}
    job_id = _upload(phone, write_photo(tmp_path / "a.jpg", seed=1), headers=bearer)

    asked = phone.get(f"/api/upload/jobs/{job_id}", headers=bearer)

    assert asked.status_code == 200 and asked.json()["status"] == "queued"


def test_guests_and_strangers_are_refused(admin: TestClient, tmp_path: Path) -> None:
    job_id = _upload(admin, write_photo(tmp_path / "a.jpg", seed=1))
    guest = add_user(admin, "gus", "guest")
    stranger = TestClient(admin.app, base_url=BASE)

    assert guest.get(f"/api/upload/jobs/{job_id}").status_code == 403
    assert stranger.get(f"/api/upload/jobs/{job_id}").status_code == 401
    assert admin.get(f"/api/upload/jobs/{2**63}").status_code == 404
