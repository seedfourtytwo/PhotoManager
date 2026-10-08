"""A job's ``updated_at`` is when it finished, not when it was claimed: finished jobs are kept
for 7 days from the end of their run."""

from datetime import datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.worker import Worker
from photo_assistant.domain.model import ImportReport, RunStatus
from tests.factories import NOW

HOUR = timedelta(hours=1)


class MovableClock:
    def __init__(self) -> None:
        self.current = NOW

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


def _updated_at(repo: SqliteRepository, job_id: int) -> datetime:
    row = repo._conn.execute("SELECT updated_at FROM job WHERE id = ?", (job_id,)).fetchone()
    return datetime.fromisoformat(row[0])


def test_a_finished_job_records_when_it_finished(repo: SqliteRepository) -> None:
    job_id = repo.enqueue("backup_run", {})
    repo.claim_next_job(NOW)
    repo.complete_job(job_id, NOW + 3 * HOUR)
    assert _updated_at(repo, job_id) == NOW + 3 * HOUR


def test_a_failed_job_records_when_it_failed(repo: SqliteRepository) -> None:
    job_id = repo.enqueue("backup_run", {})
    repo.claim_next_job(NOW)
    repo.fail_job(job_id, "boom", retry=False, now=NOW + 2 * HOUR)
    assert _updated_at(repo, job_id) == NOW + 2 * HOUR


def test_the_worker_stamps_the_end_of_a_long_job(repo: SqliteRepository) -> None:
    clock = MovableClock()

    def long_backup(payload: dict[str, object]) -> None:
        clock.current += 5 * HOUR

    def long_failure(payload: dict[str, object]) -> None:
        clock.current += 2 * HOUR
        raise ConnectionError("offline")

    done, failed = repo.enqueue("backup", {}), repo.enqueue("pull", {})
    Worker(repo, {"backup": long_backup, "pull": long_failure}, clock).run_until_idle()

    assert _updated_at(repo, done) == NOW + 5 * HOUR
    assert _updated_at(repo, failed) == NOW + 7 * HOUR


def test_seven_days_of_history_count_from_the_end_of_the_run(repo: SqliteRepository) -> None:
    """Claimed more than 7 days ago, finished less than 7 days ago: still in the history."""
    week = timedelta(days=7)
    job_id = repo.enqueue("backup_run", {})
    repo.claim_next_job(NOW - week - HOUR)
    repo.complete_job(job_id, NOW - week + HOUR)

    assert repo.prune_done_jobs(NOW - week) == 0
    assert repo.prune_done_jobs(NOW - week + 2 * HOUR) == 1


def test_a_sources_next_check_still_counts_from_the_start_of_its_last_check(
    repo: SqliteRepository,
) -> None:
    """The finish time on the job must not push an hourly check to "an hour after the end"."""
    source = repo.add_source("Pictures", "/photos")
    job_id = repo.enqueue("scan_source", {"source_id": source.id})
    repo.claim_next_job(NOW)
    repo.save_import_report(ImportReport(source.id, RunStatus.DONE), NOW, NOW + HOUR)
    repo.complete_job(job_id, NOW + HOUR)

    assert repo.last_check_attempts("scan_source") == {source.id: NOW}


def test_a_check_that_failed_before_any_report_counts_from_its_failure(
    repo: SqliteRepository,
) -> None:
    source = repo.add_source("Cloud", "/staging/1")
    job_id = repo.enqueue("scan_source", {"source_id": source.id})
    repo.claim_next_job(NOW)
    repo.fail_job(job_id, "offline", retry=False, now=NOW + HOUR)

    assert repo.last_check_attempts("scan_source") == {source.id: NOW + HOUR}
