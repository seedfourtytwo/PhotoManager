"""GET /api/jobs?status=waiting: the jobs that failed and wait for their next attempt, which
/api/stats counts as ``waiting``. The admin screen lists them with the time of that attempt."""

from datetime import timedelta

from fastapi.testclient import TestClient

from tests.api.conftest import add_user, services_of


def test_the_jobs_waiting_for_a_retry_are_listed_by_themselves(admin: TestClient) -> None:
    services = services_of(admin)
    repo, now = services.repo, services.clock.now()
    due = repo.enqueue("geocode", {})
    retrying = repo.enqueue("scan_source", {"source_id": 7})
    gone = repo.enqueue("preview", {"asset_id": 1})
    for _ in range(3):
        repo.claim_next_job(now)
    repo.release_job(due)
    repo.fail_job(retrying, "SyncError: offline", retry=True, run_after=now + timedelta(minutes=5))
    repo.fail_job(gone, "boom", retry=False)

    waiting = admin.get("/api/jobs", params={"status": "waiting"}).json()

    assert [job["id"] for job in waiting] == [retrying]
    (job,) = waiting
    assert job["status"] == "queued" and job["error"] == "SyncError: offline"
    assert job["run_after"] == (now + timedelta(minutes=5)).isoformat()
    assert admin.get("/api/stats").json()["jobs"]["waiting"] == 1
    assert {j["id"] for j in admin.get("/api/jobs", params={"status": "queued"}).json()} == {
        due,
        retrying,
    }, "the queued list is unchanged: it still holds both"
    assert [j["id"] for j in admin.get("/api/jobs", params={"status": "failed"}).json()] == [gone]


def test_only_admins_list_waiting_jobs(admin: TestClient) -> None:
    lea = add_user(admin, "lea")
    assert lea.get("/api/jobs", params={"status": "waiting"}).status_code == 403
