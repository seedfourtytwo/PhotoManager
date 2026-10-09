"""The default number of attempts uses the whole backoff schedule, and the crash-loop guard
follows the same number."""

from datetime import datetime, timedelta

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.worker import Worker
from photo_assistant.domain.job_queue import CLAIM_STALE_AFTER, MAX_ATTEMPTS, RETRY_DELAYS
from tests.factories import NOW


class MovableClock:
    def __init__(self) -> None:
        self.current = NOW

    def now(self) -> datetime:
        return self.current


def _repo() -> SqliteRepository:
    return SqliteRepository(Database.open(":memory:"))


def test_every_wait_of_the_schedule_is_used_before_a_job_fails_for_good() -> None:
    assert MAX_ATTEMPTS == len(RETRY_DELAYS) + 1 == 4


def test_an_outage_of_half_an_hour_is_covered_by_default() -> None:
    repo, clock = _repo(), MovableClock()
    calls: list[datetime] = []

    def offline(payload: dict[str, object]) -> None:
        calls.append(clock.now())
        if clock.now() < NOW + timedelta(minutes=30):
            raise ConnectionError("offline")

    repo.enqueue("pull", {})
    worker = Worker(repo, {"pull": offline}, clock)
    for _ in range(4):
        worker.run_until_idle()
        queued = repo.list_jobs("queued")
        if queued:
            clock.current = datetime.fromisoformat(str(queued[0]["run_after"]))

    assert calls == [NOW + timedelta(minutes=m) for m in (0, 1, 6, 31)]
    assert len(repo.list_jobs("done")) == 1 and not repo.list_jobs("failed")


def test_a_job_that_never_recovers_fails_after_the_fourth_attempt() -> None:
    repo, clock = _repo(), MovableClock()

    def offline(payload: dict[str, object]) -> None:
        raise ConnectionError("offline")

    repo.enqueue("pull", {})
    worker = Worker(repo, {"pull": offline}, clock)
    for _ in range(5):
        worker.run_until_idle()
        clock.current += RETRY_DELAYS[-1]
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 4 and failed["run_after"] is None


def test_the_crash_loop_guard_allows_as_many_starts_as_a_failing_job_gets_attempts() -> None:
    repo = _repo()
    ran: list[object] = []
    repo.enqueue("crashy", {})
    for _ in range(4):  # claimed, the process dies, its stale claim is requeued
        assert repo.claim_next_job(NOW) is not None
        assert repo.requeue_stale_jobs(stale_before=NOW + CLAIM_STALE_AFTER) == 1

    worker = Worker(repo, {"crashy": ran.append}, MovableClock())
    assert worker.run_once() is True
    assert ran == [], "not run a fifth time"
    (failed,) = repo.list_jobs("failed")
    assert "4 attempts" in str(failed["error"])


def test_a_job_interrupted_three_times_still_runs_its_fourth_attempt() -> None:
    repo = _repo()
    ran: list[object] = []
    repo.enqueue("flaky", {})
    for _ in range(3):
        repo.claim_next_job(NOW)
        repo.requeue_stale_jobs(stale_before=NOW + CLAIM_STALE_AFTER)
    Worker(repo, {"flaky": ran.append}, MovableClock()).run_until_idle()
    assert ran == [{}] and len(repo.list_jobs("done")) == 1
