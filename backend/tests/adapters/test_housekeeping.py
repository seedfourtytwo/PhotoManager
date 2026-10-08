"""Tables that only ever grew are pruned: failed logins, dead sessions, the AI log and the
per-file rows of old import runs."""

import sqlite3
from datetime import timedelta

import pytest

from photo_assistant.adapters.sqlite_integrations import SqliteAILog
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.domain.access import Role
from photo_assistant.domain.model import ImportReport, ItemResult, Outcome, RunStatus
from photo_assistant.ports.ai import AICall
from tests.factories import NOW


@pytest.fixture
def conn() -> sqlite3.Connection:
    return open_database(":memory:")


@pytest.fixture
def repo(conn: sqlite3.Connection) -> SqliteRepository:
    return SqliteRepository(conn)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_old_login_failures_are_forgotten_and_recent_ones_still_count(
    conn: sqlite3.Connection, repo: SqliteRepository
) -> None:
    repo.record_login_attempt(
        "nobody", "10.0.0.1", NOW - timedelta(days=3), NOW - timedelta(days=3)
    )
    repo.record_login_attempt(
        "nobody", "10.0.0.1", NOW - timedelta(hours=1), NOW - timedelta(hours=1)
    )
    repo.record_login_attempt(
        "Lea", "10.0.0.2", NOW - timedelta(minutes=1), NOW - timedelta(minutes=1)
    )
    assert repo.prune_login_failures(NOW - timedelta(hours=1)) == 1
    kept = conn.execute("SELECT username FROM login_failure ORDER BY username").fetchall()
    assert [row[0] for row in kept] == ["Lea", "nobody"]
    assert repo.prune_login_failures(NOW - timedelta(hours=1)) == 0


def test_sessions_idle_for_longer_than_the_limit_are_deleted(repo: SqliteRepository) -> None:
    user = repo.add_user("lea", "Lea", "h", Role.MEMBER)
    repo.add_session("stale", user.id, NOW - timedelta(days=40))
    repo.add_session("revived", user.id, NOW - timedelta(days=40))
    repo.touch_session("revived", NOW - timedelta(days=1))
    repo.add_session("on the limit", user.id, NOW - timedelta(days=30))
    assert repo.prune_sessions(NOW - timedelta(days=30)) == 1
    assert repo.session_user("stale") is None
    assert repo.session_user("revived") is not None
    assert repo.session_user("on the limit") is not None, "not expired yet: left alone"


def test_the_ai_log_keeps_only_recent_calls(conn: sqlite3.Connection) -> None:
    log = SqliteAILog(conn)
    for _ in range(3):
        log.record(AICall("caption", "m", {}, {}, True, 1, None, 1))
    conn.execute("UPDATE ai_log SET created_at = '2026-06-01T08:00:00.000Z' WHERE id = 1")
    conn.execute("UPDATE ai_log SET created_at = '2026-09-28T12:00:00.000Z' WHERE id = 2")
    assert log.prune(NOW - timedelta(days=1)) == 1  # NOW is 2026-09-29T12:00 UTC
    assert [r[0] for r in conn.execute("SELECT id FROM ai_log ORDER BY id")] == [2, 3]


def _run(repo: SqliteRepository, source_id: int, files: int) -> int:
    report = ImportReport(source_id=source_id, status=RunStatus.DONE, ignored=1)
    for n in range(files):
        report.add(ItemResult(f"{n}.jpg", Outcome.DUPLICATE))
    return repo.save_import_report(report, NOW, NOW)


def test_old_import_runs_keep_their_summary_but_not_their_file_lists(
    conn: sqlite3.Connection, repo: SqliteRepository
) -> None:
    a, b = repo.add_source("a", "/a"), repo.add_source("b", "/b")
    a_runs = [_run(repo, a.id, files=3) for _ in range(4)]
    b_runs = [_run(repo, b.id, files=2) for _ in range(2)]
    assert repo.prune_import_items(keep_runs=2) == 2 * 3, "the two oldest runs of source a"
    assert _count(conn, "import_run") == 6, "every run is still listed"
    assert [len(_items(repo, r)) for r in a_runs] == [0, 0, 3, 3]
    assert [len(_items(repo, r)) for r in b_runs] == [2, 2]
    oldest = repo.list_import_runs(a.id)[-1]
    assert oldest["id"] == a_runs[0]
    assert oldest["summary"] == {
        "imported": 0, "duplicate": 3, "already_known": 0, "skipped": 0, "failed": 0,
        "ignored": 1, "files_seen": 4,
    }  # fmt: skip
    assert repo.import_run_summary(a_runs[0]) == oldest["summary"]
    assert repo.import_run_summary(999) is None
    assert repo.prune_import_items(keep_runs=2) == 0


def _items(repo: SqliteRepository, run_id: int) -> list[ItemResult]:
    report = repo.get_import_report(run_id)
    assert report is not None
    return report.items


def test_the_list_of_import_runs_is_bounded_newest_first(repo: SqliteRepository) -> None:
    source = repo.add_source("a", "/a")
    runs = [_run(repo, source.id, files=0) for _ in range(5)]
    assert [r["id"] for r in repo.list_import_runs(source.id, limit=2)] == runs[:2:-1]
    assert [r["id"] for r in repo.list_import_runs(limit=3)] == runs[:1:-1]
    assert len(repo.list_import_runs()) == 5
