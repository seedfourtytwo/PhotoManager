"""GET /api/imports/{id} answers a page of the run's files, never all 100,000 of a big
rescan; the summary counts stay those of the whole run."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from photo_assistant.domain.model import ImportReport, ItemResult, Outcome, RunStatus
from tests.api.conftest import services_of

NOW = datetime(2026, 5, 1, tzinfo=UTC)


def _run(admin: TestClient, known: int, failed: int = 0, skipped: int = 0) -> int:
    """A run whose files were mostly seen before, with the problems scattered at the end."""
    repo = services_of(admin).repo
    source = repo.add_source("Pictures", "/photos")
    items = [ItemResult(f"known-{n:05}.jpg", Outcome.ALREADY_KNOWN) for n in range(known)]
    items += [ItemResult(f"clip-{n}.mov", Outcome.SKIPPED, "video") for n in range(skipped)]
    items += [ItemResult(f"bad-{n}.jpg", Outcome.FAILED, "truncated") for n in range(failed)]
    return repo.save_import_report(ImportReport(source.id, RunStatus.DONE, items), NOW, NOW)


def _paths(body: dict[str, object]) -> list[str]:
    return [item["relative_path"] for item in body["items"]]  # type: ignore[union-attr,index]


def test_a_big_run_answers_its_first_500_files_and_how_many_there_are(admin: TestClient) -> None:
    run_id = _run(admin, known=1200)

    body = admin.get(f"/api/imports/{run_id}").json()

    assert len(body["items"]) == 500
    assert (body["total"], body["limit"], body["offset"]) == (1200, 500, 0)
    assert body["next_offset"] == 500
    assert body["summary"]["already_known"] == 1200, "the counts are the whole run's"
    assert body["summary"]["files_seen"] == 1200


def test_a_small_run_answers_everything_as_before(admin: TestClient) -> None:
    run_id = _run(admin, known=3, failed=1)

    body = admin.get(f"/api/imports/{run_id}").json()

    assert set(body) == {
        "id", "source_id", "status", "message", "summary", "items",
        "total", "limit", "offset", "next_offset",
    }  # fmt: skip
    assert body["items"][0] == {
        "relative_path": "bad-0.jpg",
        "outcome": "failed",
        "reason": "truncated",
        "asset_id": None,
    }
    assert (body["total"], body["next_offset"]) == (4, None)


def test_the_files_that_need_a_look_come_first(admin: TestClient) -> None:
    """Failures of a rescan must not hide behind 100,000 files that were seen before."""
    run_id = _run(admin, known=600, failed=2, skipped=1)

    first = _paths(admin.get(f"/api/imports/{run_id}", params={"limit": 4}).json())

    assert first == ["bad-0.jpg", "bad-1.jpg", "clip-0.mov", "known-00000.jpg"]


def test_the_following_pages_continue_where_the_last_one_ended(admin: TestClient) -> None:
    run_id = _run(admin, known=5, failed=1)
    seen: list[str] = []
    offset: int | None = 0
    while offset is not None:
        body = admin.get(f"/api/imports/{run_id}", params={"limit": 4, "offset": offset}).json()
        seen += _paths(body)
        offset = body["next_offset"]

    assert seen == ["bad-0.jpg", *(f"known-{n:05}.jpg" for n in range(5))]


def test_one_outcome_is_counted_and_paged_by_itself(admin: TestClient) -> None:
    run_id = _run(admin, known=10, failed=3)

    body = admin.get(f"/api/imports/{run_id}", params={"outcome": "failed", "limit": 2}).json()

    assert _paths(body) == ["bad-0.jpg", "bad-1.jpg"]
    assert (body["total"], body["next_offset"]) == (3, 2)
    assert body["summary"]["already_known"] == 10


def test_a_page_past_the_end_is_empty(admin: TestClient) -> None:
    run_id = _run(admin, known=2)
    body = admin.get(f"/api/imports/{run_id}", params={"offset": 50}).json()
    assert (body["items"], body["total"], body["next_offset"]) == ([], 2, None)


def test_the_page_size_has_limits(admin: TestClient) -> None:
    run_id = _run(admin, known=1)
    assert admin.get(f"/api/imports/{run_id}", params={"limit": 2000}).status_code == 200
    for bad in ({"limit": 2001}, {"limit": 0}, {"offset": -1}):
        assert admin.get(f"/api/imports/{run_id}", params=bad).status_code == 422, bad


def test_an_unknown_run_is_still_not_found(admin: TestClient) -> None:
    response = admin.get("/api/imports/999", params={"limit": 10})
    assert (response.status_code, response.json()) == (404, {"detail": "import run not found"})
