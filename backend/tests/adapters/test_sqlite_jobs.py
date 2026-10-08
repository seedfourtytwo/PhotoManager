"""The job table as a queue: retries that wait their turn, claims with an owner and a lease,
and the indexes the polling statements rely on (migration 0022)."""

import sqlite3
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from tests.factories import NOW, new_asset

MINUTE = timedelta(minutes=1)


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(Database.open(":memory:"))


def _row(repo: SqliteRepository, job_id: int) -> sqlite3.Row:
    row = repo._conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    return row  # type: ignore[no-any-return]


# --- retries wait their turn ---------------------------------------------------------------


def test_a_job_failed_for_a_later_retry_is_not_claimed_before_its_time(
    repo: SqliteRepository,
) -> None:
    job_id = repo.enqueue("pull", {})
    assert repo.claim_next_job(NOW) is not None
    repo.fail_job(job_id, "network down", retry=True, run_after=NOW + MINUTE)

    assert repo.claim_next_job(NOW) is None
    assert repo.claim_next_job(NOW + MINUTE - timedelta(seconds=1)) is None
    again = repo.claim_next_job(NOW + MINUTE)
    assert again is not None and again.id == job_id and again.attempts == 2


def test_a_waiting_retry_does_not_hold_up_the_jobs_behind_it(repo: SqliteRepository) -> None:
    first = repo.enqueue("pull", {"n": 1})
    second = repo.enqueue("pull", {"n": 2})
    assert repo.claim_next_job(NOW) is not None
    repo.fail_job(first, "network down", retry=True, run_after=NOW + MINUTE)
    behind = repo.claim_next_job(NOW)
    assert behind is not None and behind.id == second


def test_a_failure_for_good_is_never_claimed_again(repo: SqliteRepository) -> None:
    job_id = repo.enqueue("pull", {})
    repo.claim_next_job(NOW)
    repo.fail_job(job_id, "folder is gone", retry=False)
    assert repo.claim_next_job(NOW + 100 * MINUTE) is None
    assert _row(repo, job_id)["run_after"] is None


def test_retry_by_hand_runs_at_once_even_while_the_job_was_waiting(
    repo: SqliteRepository,
) -> None:
    job_id = repo.enqueue("pull", {})
    repo.claim_next_job(NOW)
    repo.fail_job(job_id, "network down", retry=True, run_after=NOW + 25 * MINUTE)
    repo.claim_next_job(NOW + 25 * MINUTE)
    repo.fail_job(job_id, "still down", retry=False)
    repo._conn.execute("UPDATE job SET run_after = ? WHERE id = ?", ("9999-01-01", job_id))

    assert repo.retry_job(job_id) is True
    now = repo.claim_next_job(NOW)
    assert now is not None and now.id == job_id and now.attempts == 1


def test_the_listing_says_until_when_a_retry_waits(repo: SqliteRepository) -> None:
    waiting = repo.enqueue("pull", {})
    fresh = repo.enqueue("pull", {})
    repo.claim_next_job(NOW)
    repo.fail_job(waiting, "network down", retry=True, run_after=NOW + MINUTE)
    rows = {job["id"]: job for job in repo.list_jobs("queued")}
    assert rows[waiting]["run_after"] == (NOW + MINUTE).isoformat()
    assert rows[waiting]["error"] == "network down"
    assert rows[fresh]["run_after"] is None


def test_a_waiting_retry_is_counted_apart_from_the_work_that_is_due(
    repo: SqliteRepository,
) -> None:
    """The screens that wait for "nothing queued, nothing running" (admin, upload) must not
    sit through a retry's wait of minutes."""
    waiting = repo.enqueue("pull", {})
    repo.enqueue("preview", {})
    repo.claim_next_job(NOW)
    repo.fail_job(waiting, "network down", retry=True, run_after=NOW + MINUTE)
    assert repo.job_counts() == {"queued": 1, "waiting": 1, "running": 0, "done": 0, "failed": 0}


def test_a_job_put_back_because_the_library_was_busy_is_free_again(
    repo: SqliteRepository,
) -> None:
    job_id = repo.enqueue("scan", {})
    repo.claim_next_job(NOW, owner="server-1")
    repo.release_job(job_id)
    row = _row(repo, job_id)
    assert (row["status"], row["attempts"], row["claimed_by"], row["claimed_at"]) == (
        "queued",
        0,
        None,
        None,
    )


# --- ownership and lease -------------------------------------------------------------------


@pytest.fixture
def two_processes(tmp_path: Path) -> tuple[SqliteRepository, SqliteRepository]:
    """Two connections to one database file: the server and a CLI command."""
    db = tmp_path / "library.db"
    return SqliteRepository(Database.open(db)), SqliteRepository(Database.open(db))


def test_a_claim_records_who_took_the_job_and_when(repo: SqliteRepository) -> None:
    job_id = repo.enqueue("backup_run", {})
    repo.claim_next_job(NOW, owner="server-1")
    row = _row(repo, job_id)
    assert (row["claimed_by"], row["claimed_at"]) == ("server-1", NOW.isoformat())


def test_a_fresh_job_of_another_live_process_is_not_requeued(
    two_processes: tuple[SqliteRepository, SqliteRepository],
) -> None:
    cli, server = two_processes
    job_id = cli.enqueue("preview", {})
    cli.claim_next_job(NOW, owner="cli-1")

    assert server.requeue_stale_jobs(stale_before=NOW - 5 * MINUTE) == 0
    assert _row(server, job_id)["status"] == "running"
    assert server.claim_next_job(NOW, owner="server-1") is None, "it would run twice"


def test_a_job_whose_owner_stopped_renewing_is_requeued_and_the_run_counts(
    two_processes: tuple[SqliteRepository, SqliteRepository],
) -> None:
    cli, server = two_processes
    job_id = cli.enqueue("preview", {})
    cli.claim_next_job(NOW, owner="cli-1")  # … and the CLI process is killed

    later = NOW + 6 * MINUTE
    assert server.requeue_stale_jobs(stale_before=later - 5 * MINUTE) == 1
    row = _row(server, job_id)
    assert (row["status"], row["claimed_by"], row["claimed_at"]) == ("queued", None, None)
    again = server.claim_next_job(later, owner="server-1")
    assert again is not None and again.attempts == 2, "the run that died was an attempt"


def test_renewing_the_claim_keeps_a_long_job_fresh(
    two_processes: tuple[SqliteRepository, SqliteRepository],
) -> None:
    server, other = two_processes
    job_id = server.enqueue("backup_run", {})
    server.claim_next_job(NOW, owner="server-1")
    hours_later = NOW + timedelta(hours=3)
    server.renew_claim(job_id, "server-1", hours_later - MINUTE)

    assert other.requeue_stale_jobs(stale_before=hours_later - 5 * MINUTE) == 0
    assert _row(other, job_id)["status"] == "running"


def test_only_the_owner_can_renew_a_claim(
    two_processes: tuple[SqliteRepository, SqliteRepository],
) -> None:
    """A process that was wrongly given up on must not keep a job fresh that another one has
    taken over since."""
    first, second = two_processes
    job_id = first.enqueue("backup_run", {})
    first.claim_next_job(NOW, owner="cli-1")
    first.requeue_stale_jobs(stale_before=NOW + MINUTE)
    second.claim_next_job(NOW + MINUTE, owner="server-1")

    first.renew_claim(job_id, "cli-1", NOW + 10 * MINUTE)
    row = _row(second, job_id)
    assert (row["claimed_by"], row["claimed_at"]) == ("server-1", (NOW + MINUTE).isoformat())


def test_a_job_left_running_by_a_version_without_leases_counts_as_stale(
    repo: SqliteRepository,
) -> None:
    job_id = repo.enqueue("preview", {})
    repo._conn.execute("UPDATE job SET status = 'running', attempts = 1 WHERE id = ?", (job_id,))
    assert repo.requeue_stale_jobs(stale_before=NOW) == 1
    assert _row(repo, job_id)["status"] == "queued"


def test_finished_and_failed_jobs_are_never_requeued(repo: SqliteRepository) -> None:
    done, failed = repo.enqueue("a", {}), repo.enqueue("b", {})
    repo.claim_next_job(NOW, owner="server-1")
    repo.claim_next_job(NOW, owner="server-1")
    repo.complete_job(done)
    repo.fail_job(failed, "boom", retry=False)
    assert repo.requeue_stale_jobs(stale_before=NOW + 100 * MINUTE) == 0
    assert {_row(repo, i)["status"] for i in (done, failed)} == {"done", "failed"}


# --- the polling statements use their indexes ----------------------------------------------


def _plans(repo: SqliteRepository, action: Callable[[], object]) -> list[str]:
    """The query plan of every statement ``action`` runs, as SQLite would run it now."""
    statements: list[str] = []
    repo._conn.set_trace_callback(statements.append)
    try:
        action()
    finally:
        repo._conn.set_trace_callback(None)
    plans = []
    for sql in statements:
        if sql.split(None, 1)[0].upper() in {"BEGIN", "COMMIT", "ROLLBACK"}:
            continue
        plans += [str(row["detail"]) for row in repo._conn.execute(f"EXPLAIN QUERY PLAN {sql}")]
    return plans


def _reads_of(plans: list[str], table: str) -> list[str]:
    return [p for p in plans if p.startswith((f"SCAN {table}", f"SEARCH {table}"))]


@pytest.fixture
def busy_queue(repo: SqliteRepository) -> SqliteRepository:
    """Finished history, a pile of waiting previews and one geocode job behind them."""
    repo._conn.executemany(
        "INSERT INTO job (kind, payload_json, status) VALUES ('preview', '{}', ?)",
        [("done",)] * 200 + [("queued",)] * 200,
    )
    repo.enqueue_once("geocode")
    repo._conn.execute("ANALYZE")
    return repo


@pytest.mark.parametrize(
    "lane",
    [
        {},
        {"only": ["preview"]},
        {"only": ["scan_source", "backup_run"]},
        {"excluding": ["preview", "scan_source", "backup_run"]},
    ],
    ids=["every kind", "preview pool", "long lane", "quick lane"],
)
def test_claiming_never_walks_the_waiting_jobs_of_other_lanes(
    busy_queue: SqliteRepository, lane: dict[str, list[str]]
) -> None:
    plans = _plans(busy_queue, lambda: busy_queue.claim_next_job(NOW, **lane))
    reads = [p for p in _reads_of(plans, "job") if "INTEGER PRIMARY KEY" not in p]
    assert reads, plans
    assert all("INDEX job_waiting" in p for p in reads), plans


def test_enqueue_once_looks_only_at_waiting_jobs_of_its_kind(
    busy_queue: SqliteRepository,
) -> None:
    plans = _plans(busy_queue, lambda: busy_queue.enqueue_once("geocode"))
    assert _reads_of(plans, "job") == ["SEARCH job USING INDEX job_waiting (kind=?)"], plans


def test_purging_a_photo_finds_its_variants_by_index(repo: SqliteRepository) -> None:
    asset_id = repo.add_asset(new_asset(1), NOW)
    variant = repo.add_asset(new_asset(2), NOW)
    repo.set_variant_of(variant, asset_id)
    repo._conn.execute("UPDATE asset SET trashed_at = ? WHERE id = ?", (NOW.isoformat(), asset_id))
    asset = repo.get_asset(asset_id)
    assert asset is not None

    plans = _plans(repo, lambda: repo.purge_asset(asset, NOW))

    # the UPDATE that clears the variants, and the foreign-key check of DELETE FROM asset
    lookups = [p for p in plans if "variant_of" in p]
    assert len(lookups) >= 2, plans
    assert all("INDEX asset_by_variant_of (variant_of=?)" in p for p in lookups), plans
    assert "SCAN asset" not in plans, "variants and look-alikes are both found by index"
    assert repo.get_asset(asset_id) is None
    still = repo.get_asset(variant)
    assert still is not None and still.variant_of is None
