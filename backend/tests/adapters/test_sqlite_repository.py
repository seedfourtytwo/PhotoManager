import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_access import UnknownUserError
from photo_assistant.adapters.sqlite_repository import (
    DuplicateAssetError,
    SqliteRepository,
    open_database,
)
from photo_assistant.domain.access import Level, Role, SourceAccess
from photo_assistant.domain.model import ImportReport, ItemResult, Outcome, RunStatus
from photo_assistant.ports import Fingerprint, RenderedImage
from tests.factories import NOW, new_asset


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


# --- migrations ----------------------------------------------------------------------------


def test_fresh_database_is_migrated_to_latest(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "library.db", backup_dir=tmp_path / "backups")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 1
    assert not (tmp_path / "backups").exists(), "a brand-new database needs no snapshot"


def test_existing_database_is_snapshotted_before_migrating(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    sqlite3.connect(db).execute("CREATE TABLE legacy (x)").connection.commit()
    open_database(db, backup_dir=tmp_path / "backups")
    snapshots = list((tmp_path / "backups").glob("library-v0-*.db"))
    assert len(snapshots) == 1
    tables = sqlite3.connect(snapshots[0]).execute("SELECT name FROM sqlite_master").fetchall()
    assert ("legacy",) in tables


def test_reopening_a_current_database_changes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    open_database(db, backup_dir=tmp_path / "backups").close()
    open_database(db, backup_dir=tmp_path / "backups").close()
    assert not (tmp_path / "backups").exists()


# --- sources -------------------------------------------------------------------------------


def test_sources_round_trip(repo: SqliteRepository) -> None:
    a = repo.add_source("Laptop Pictures", "/home/c/Pictures")
    b = repo.add_source("Old HDD", "/media/old")
    assert [s.label for s in repo.list_sources()] == ["Laptop Pictures", "Old HDD"]
    repo.set_source_enabled(b.id, False)
    got = repo.get_source(b.id)
    assert got is not None and not got.enabled
    assert repo.get_source(a.id) == a
    assert repo.get_source(999) is None


def test_the_same_folder_cannot_be_added_twice(repo: SqliteRepository) -> None:
    repo.add_source("one", "/x")
    with pytest.raises(ValueError, match="already"):
        repo.add_source("two", "/x")


def test_a_source_for_an_unknown_account_is_not_reported_as_a_duplicate_folder(
    repo: SqliteRepository,
) -> None:
    lea = repo.add_user("lea", "Lea", "h", Role.MEMBER)
    with pytest.raises(UnknownUserError, match="no user with id 99"):
        repo.add_source("owner", "/owner", owner_id=99)
    with pytest.raises(UnknownUserError, match="no user with id 77"):
        repo.add_source(
            "grant",
            "/grant",
            lea.id,
            access=SourceAccess(None, ((lea.id, Level.EDIT), (77, Level.VIEW))),
        )
    with pytest.raises(UnknownUserError, match="no user with id 99"):
        repo.add_source("remote", lambda source_id: f"/staging/{source_id}", owner_id=99)
    assert repo.list_sources() == [], "nothing half-made is left behind"


def test_a_folder_clash_names_the_folder_even_when_the_root_depends_on_the_id(
    repo: SqliteRepository,
) -> None:
    repo.add_source("one", "/staging/taken")
    with pytest.raises(ValueError, match="already a source: /staging/taken"):
        repo.add_source("two", lambda _source_id: "/staging/taken")
    assert [s.label for s in repo.list_sources()] == ["one"]


# --- assets --------------------------------------------------------------------------------


def test_asset_round_trip_keeps_every_field(repo: SqliteRepository) -> None:
    new = new_asset(7, latitude=48.85, longitude=2.35, tz_offset_minutes=120)
    asset_id = repo.add_asset(new, imported_at=NOW)
    got = repo.get_asset(asset_id)
    assert got is not None
    for field in new.__slots__:  # type: ignore[attr-defined]
        assert getattr(got, field) == getattr(new, field), field
    assert repo.find_asset_id_by_hash(new.content_hash) == asset_id
    assert repo.find_asset_id_by_hash("f" * 64) is None
    assert repo.count_assets() == 1


def test_timeline_is_newest_first_with_stable_cursor_paging(repo: SqliteRepository) -> None:
    base = datetime(2020, 1, 1)
    for n in range(1, 8):
        repo.add_asset(new_asset(n, taken_at=base + timedelta(days=n % 4)), imported_at=NOW)
    seen: list[int] = []
    cursor = None
    while True:
        page = repo.list_assets(limit=3, cursor=cursor)
        seen += [a.id for a in page.items]
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert len(seen) == len(set(seen)) == 7
    everything = repo.list_assets(limit=100).items
    keys = [(a.taken_at, a.id) for a in everything]
    assert keys == sorted(keys, reverse=True)
    assert seen == [a.id for a in everything]


def test_bad_cursor_is_rejected(repo: SqliteRepository) -> None:
    with pytest.raises(ValueError, match="cursor"):
        repo.list_assets(limit=3, cursor="not-a-cursor")


def test_derivatives_and_variants_are_recorded(repo: SqliteRepository) -> None:
    original = repo.add_asset(new_asset(1), imported_at=NOW)
    edit = repo.add_asset(new_asset(2), imported_at=NOW)
    repo.set_thumbnail(original, RenderedImage("derived/thumb/aa/x.webp", 640, 480))
    repo.set_preview(original, RenderedImage("derived/preview/aa/x.webp", 2048, 1536))
    repo.set_variant_of(edit, original)
    got = repo.get_asset(original)
    assert got is not None and got.thumb_path == "derived/thumb/aa/x.webp"
    assert got.preview_path == "derived/preview/aa/x.webp"
    edited = repo.get_asset(edit)
    assert edited is not None and edited.variant_of == original


def test_asset_sources_track_every_origin(repo: SqliteRepository) -> None:
    s1 = repo.add_source("a", "/a")
    s2 = repo.add_source("b", "/b")
    asset_id = repo.add_asset(new_asset(1), imported_at=NOW)
    repo.add_asset_source(asset_id, s1.id, "x.jpg")
    repo.add_asset_source(asset_id, s2.id, "copy/x.jpg")
    repo.add_asset_source(asset_id, s2.id, "copy/x.jpg")  # idempotent
    assert repo.asset_id_for_source_path(s1.id, "x.jpg") == asset_id
    assert repo.asset_id_for_source_path(s1.id, "y.jpg") is None
    assert repo.asset_id_for_source_path(s2.id, "copy/x.jpg") == asset_id
    assert repo.asset_id_for_source_path(s2.id, "nope.jpg") is None
    origins = repo._conn.execute(
        "SELECT source_id, relative_path FROM asset_source WHERE asset_id = ? ORDER BY 1, 2",
        (asset_id,),
    ).fetchall()
    assert [tuple(r) for r in origins] == [(s1.id, "x.jpg"), (s2.id, "copy/x.jpg")]


# --- import runs ---------------------------------------------------------------------------


def test_import_report_round_trip(repo: SqliteRepository) -> None:
    source = repo.add_source("a", "/a")
    report = ImportReport(source_id=source.id, status=RunStatus.DONE, ignored=2)
    report.add(ItemResult("a.jpg", Outcome.IMPORTED, asset_id=1))
    report.add(ItemResult("France.pdf", Outcome.SKIPPED, "not a photo (pdf)"))
    run_id = repo.save_import_report(report, NOW, NOW + timedelta(seconds=5))
    got = repo.get_import_report(run_id)
    assert got is not None
    assert got.items == report.items
    assert got.ignored == 2 and got.status is RunStatus.DONE
    runs = repo.list_import_runs(source.id)
    assert runs[0]["id"] == run_id
    assert runs[0]["summary"] == report.summary()
    assert repo.get_import_report(999) is None


# --- job queue -----------------------------------------------------------------------------


def test_jobs_are_claimed_in_order_once(repo: SqliteRepository) -> None:
    first = repo.enqueue("derive", {"asset_id": 1})
    second = repo.enqueue("derive", {"asset_id": 2})
    job = repo.claim_next_job(NOW)
    assert job is not None and job.id == first and job.payload == {"asset_id": 1}
    assert job.attempts == 1
    job2 = repo.claim_next_job(NOW)
    assert job2 is not None and job2.id == second
    assert repo.claim_next_job(NOW) is None
    repo.complete_job(first)
    assert [j["id"] for j in repo.list_jobs("done")] == [first]
    assert repo.job_counts() == {"queued": 0, "waiting": 0, "running": 1, "done": 1, "failed": 0}


def test_failed_job_can_retry_then_gives_up(repo: SqliteRepository) -> None:
    job_id = repo.enqueue("derive", {"asset_id": 1})
    claimed = repo.claim_next_job(NOW)
    assert claimed is not None
    repo.fail_job(job_id, "boom", retry=True)
    again = repo.claim_next_job(NOW)
    assert again is not None and again.attempts == 2
    repo.fail_job(job_id, "boom again", retry=False)
    failed = repo.list_jobs("failed")
    assert failed[0]["error"] == "boom again"
    assert repo.retry_job(job_id) is True
    assert repo.list_jobs("queued")[0]["id"] == job_id
    assert repo.retry_job(12345) is False


def test_jobs_left_running_by_a_crash_are_requeued_once_their_claim_is_stale(
    tmp_path: Path,
) -> None:
    db = tmp_path / "library.db"
    repo = SqliteRepository(open_database(db))
    repo.enqueue("derive", {"asset_id": 1})
    assert repo.claim_next_job(NOW) is not None  # now "running"; process "crashes" here
    reopened = SqliteRepository(open_database(db))
    assert reopened.requeue_stale_jobs(stale_before=NOW) == 0, "it may still be running"
    assert reopened.requeue_stale_jobs(stale_before=NOW + timedelta(minutes=5)) == 1
    assert reopened.claim_next_job(NOW) is not None


# --- QA M1: atomic import record, cross-process job claims ---------------------------------


def test_record_import_writes_everything_in_one_go(repo: SqliteRepository) -> None:
    source = repo.add_source("s", "/s")
    asset_id = repo.record_import(
        new_asset(1),
        NOW,
        source.id,
        "a.jpg",
        RenderedImage("derived/thumb/x.webp", 64, 48),
        "preview",
    )
    asset = repo.get_asset(asset_id)
    assert asset is not None and asset.thumb_path == "derived/thumb/x.webp"
    assert repo.asset_id_for_source_path(source.id, "a.jpg") == asset_id
    assert repo.list_jobs("queued")[0]["payload"] == {"asset_id": asset_id}


def test_record_import_of_known_content_changes_nothing_and_says_which(
    repo: SqliteRepository,
) -> None:
    source = repo.add_source("s", "/s")
    thumb = RenderedImage("derived/thumb/x.webp", 64, 48)
    first = repo.record_import(new_asset(1), NOW, source.id, "a.jpg", thumb, "preview")
    with pytest.raises(DuplicateAssetError) as caught:
        repo.record_import(new_asset(1), NOW, source.id, "b.jpg", thumb, "preview")
    assert caught.value.asset_id == first
    assert repo.asset_id_for_source_path(source.id, "b.jpg") is None
    assert len(repo.list_jobs("queued")) == 1, "rolled back: no second job"


def test_import_writes_join_a_transaction_that_is_already_open(repo: SqliteRepository) -> None:
    """They go through the one transaction() like every other write, so they nest."""
    source = repo.add_source("s", "/s")
    thumb = RenderedImage("derived/thumb/x.webp", 64, 48)
    report = ImportReport(source_id=source.id, status=RunStatus.DONE)
    report.add(ItemResult("a.jpg", Outcome.IMPORTED))
    with pytest.raises(RuntimeError, match="undo"), repo._transaction():
        repo.record_import(new_asset(1), NOW, source.id, "a.jpg", thumb, "preview")
        repo.save_import_report(report, NOW, NOW)
        raise RuntimeError("undo")
    assert repo.count_assets() == 0 and repo.list_import_runs() == []
    assert not repo._conn.in_transaction


def test_two_processes_never_claim_the_same_job(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    a = SqliteRepository(open_database(db))
    b = SqliteRepository(open_database(db))
    for n in range(4):
        a.enqueue("x", {"n": n})
    claimed = [r.claim_next_job(NOW) for r in (a, b, a, b, a)]
    ids = [j.id for j in claimed if j is not None]
    assert len(ids) == 4 == len(set(ids))
    assert claimed[-1] is None


def test_upgrading_a_v1_library_keeps_its_data_and_snapshots_first(tmp_path: Path) -> None:
    from photo_assistant.adapters.sqlite_repository import _migrations

    db = tmp_path / "library.db"
    conn = sqlite3.connect(db)
    number, sql = _migrations()[0]
    assert number == 1
    conn.executescript(f"BEGIN;{sql};PRAGMA user_version = 1;COMMIT;")
    conn.execute("INSERT INTO source (label, root) VALUES ('old', '/old')")
    conn.commit()
    conn.close()

    repo = SqliteRepository(open_database(db, backup_dir=tmp_path / "backups"))

    assert [s.label for s in repo.list_sources()] == ["old"]
    assert len(list((tmp_path / "backups").glob("library-v1-*.db"))) == 1


def test_source_fingerprint_round_trip(repo: SqliteRepository) -> None:
    source = repo.add_source("s", "/s")
    asset_id = repo.add_asset(new_asset(1), imported_at=NOW)
    repo.add_asset_source(asset_id, source.id, "a.jpg", Fingerprint(123, 456, 789))
    assert repo.fingerprint_of(source.id, "a.jpg") == (asset_id, Fingerprint(123, 456, 789))
    assert repo.fingerprint_of(source.id, "b.jpg") is None
    assert repo.previous_path_in_source(asset_id, source.id, exclude="x.jpg") == "a.jpg"


def test_done_jobs_older_than_a_week_are_pruned(repo: SqliteRepository) -> None:
    """C31: the job table would otherwise grow by several rows per photo forever."""
    from datetime import timedelta

    old, recent, failed = (repo.enqueue(k, {}) for k in ("old", "recent", "failed"))
    for _ in (old, recent, failed):
        repo.claim_next_job(NOW)
    repo.complete_job(old)
    repo.complete_job(recent)
    repo.fail_job(failed, "boom", retry=False)
    repo._write(
        "UPDATE job SET updated_at = ? WHERE id IN (?, ?)",
        ((NOW - timedelta(days=8)).isoformat(), old, failed),
    )
    assert repo.prune_done_jobs(NOW - timedelta(days=7)) == 1
    assert {j["kind"] for j in repo.list_jobs()} == {"recent", "failed"}, "failures are kept"
