import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.app.derivatives import GeneratePreview
from photo_assistant.app.worker import Lanes, StaleJobSweep, Worker, new_owner_id
from photo_assistant.domain.errors import DomainError
from photo_assistant.domain.job_queue import (
    CLAIM_STALE_AFTER,
    RETRY_DELAYS,
    STALE_SWEEP_INTERVAL,
)
from tests.factories import NOW, new_asset
from tests.fakes import FakeClock


def test_worker_runs_jobs_until_idle(repo: SqliteRepository) -> None:
    done: list[object] = []
    repo.enqueue("echo", {"n": 1})
    repo.enqueue("echo", {"n": 2})
    worker = Worker(repo, {"echo": lambda payload: done.append(payload["n"])}, FakeClock())
    assert worker.run_until_idle() == 2
    assert done == [1, 2]
    assert len(repo.list_jobs("done")) == 2


def test_failing_job_is_retried_then_marked_failed_with_reason(repo: SqliteRepository) -> None:
    def boom(payload: dict[str, object]) -> None:
        raise ValueError("decoder exploded")

    repo.enqueue("boom", {})
    clock = FakeClock()
    worker = Worker(repo, {"boom": boom}, clock, max_attempts=3)
    for _ in range(3):
        worker.run_until_idle()
        clock.advance(RETRY_DELAYS[-1])  # a retry waits its turn
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 3
    assert "decoder exploded" in str(failed["error"])


def test_unknown_job_kind_fails_immediately(repo: SqliteRepository) -> None:
    repo.enqueue("mystery", {})
    Worker(repo, {}, FakeClock()).run_until_idle()
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 1 and "no handler" in str(failed["error"])


def test_background_thread_starts_and_stops_cleanly(repo: SqliteRepository) -> None:
    ran = threading.Event()
    repo.enqueue("ping", {})
    worker = Worker(repo, {"ping": lambda _: ran.set()}, FakeClock(), poll_seconds=0.01)
    worker.start()
    assert ran.wait(timeout=5)
    worker.stop()
    assert not worker.is_running


@pytest.mark.integration
def test_preview_job_renders_from_the_library_copy(repo: SqliteRepository, tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "photos" / "IMG_1002.JPG"
    store = DiskLibraryStore(tmp_path / "data")
    digest = Blake3Hasher().hash_file(fixture)
    library_path = f"originals/2020/12/{digest}.jpg"
    store.store_original(fixture, library_path, digest)
    asset_id = repo.add_asset(
        new_asset(content_hash=digest, library_path=library_path), imported_at=NOW
    )
    GeneratePreview(repo, store, VipsRenderer(), max_edge=100)({"asset_id": asset_id})
    asset = repo.get_asset(asset_id)
    assert asset is not None and asset.preview_path is not None
    assert store.absolute(asset.preview_path).is_file()


def test_a_preview_job_also_repairs_a_missing_thumbnail_from_the_same_decode(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    """C28: decode once, write both (the import's thumbnail went missing)."""
    store = DiskLibraryStore(tmp_path / "data")
    source = tmp_path / "photo.jpg"
    from tests.synthetic import write_photo

    write_photo(source, seed=3, size=(400, 300))
    digest = Blake3Hasher().hash_file(source)
    library_path = f"originals/2020/01/{digest}.jpg"
    store.store_original(source, library_path, digest)
    asset_id = repo.add_asset(new_asset(content_hash=digest, library_path=library_path), NOW)

    class OneDecode(VipsRenderer):
        decodes = 0

        def render(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            OneDecode.decodes += 1
            return super().render(*args, **kwargs)

        def render_pair(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            OneDecode.decodes += 1
            return super().render_pair(*args, **kwargs)

    GeneratePreview(repo, store, OneDecode(), max_edge=200, thumb_edge=80)({"asset_id": asset_id})
    asset = repo.get_asset(asset_id)
    assert asset is not None and asset.thumb_path and asset.preview_path
    assert asset.thumb_size == (80, 60) and OneDecode.decodes == 1
    assert store.absolute(asset.thumb_path).is_file()


def test_a_preview_job_for_a_photo_purged_meanwhile_finishes_quietly(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    job = GeneratePreview(repo, DiskLibraryStore(tmp_path), VipsRenderer())
    repo.enqueue("preview", {"asset_id": 42})
    Worker(repo, {"preview": job}, FakeClock()).run_until_idle()
    assert repo.list_jobs("failed") == [] and len(repo.list_jobs("done")) == 1


def test_busy_library_requeues_without_using_up_attempts(repo: SqliteRepository) -> None:
    from photo_assistant.ports import ImportBusyError

    calls = []

    def busy(payload: dict[str, object]) -> None:
        calls.append(1)
        if len(calls) < 5:
            raise ImportBusyError("an import into this library is already running")

    repo.enqueue("scan", {})
    worker = Worker(repo, {"scan": busy}, FakeClock(), max_attempts=3)
    for _ in range(5):
        worker.run_once()
    assert repo.list_jobs("done"), "succeeded on the 5th try although max_attempts is 3"


def test_a_job_that_keeps_killing_the_process_is_given_up_on(repo: SqliteRepository) -> None:
    """A segfault or OOM never reaches the worker's except branch: only the claims count."""
    ran: list[object] = []
    repo.enqueue("crashy", {})
    for _ in range(3):  # three starts: claimed, the process dies, its stale claim is requeued
        assert repo.claim_next_job(NOW) is not None
        assert repo.requeue_stale_jobs(stale_before=NOW + CLAIM_STALE_AFTER) == 1
    worker = Worker(repo, {"crashy": ran.append}, FakeClock(), max_attempts=3)
    assert worker.run_once() is True
    assert ran == [], "not run a fourth time"
    (failed,) = repo.list_jobs("failed")
    assert "3 attempts" in str(failed["error"])
    assert worker.run_once() is False


def test_a_job_interrupted_fewer_times_than_allowed_still_runs(repo: SqliteRepository) -> None:
    ran: list[object] = []
    repo.enqueue("flaky", {})
    for _ in range(2):
        repo.claim_next_job(NOW)
        repo.requeue_stale_jobs(stale_before=NOW + CLAIM_STALE_AFTER)
    Worker(repo, {"flaky": ran.append}, FakeClock(), max_attempts=3).run_until_idle()
    assert ran == [{}] and len(repo.list_jobs("done")) == 1


def test_a_failed_job_retried_by_hand_runs_again(repo: SqliteRepository) -> None:
    calls: list[int] = []

    def boom(payload: dict[str, object]) -> None:
        calls.append(1)
        raise ValueError("decoder exploded")

    job_id = repo.enqueue("boom", {})
    clock = FakeClock()
    worker = Worker(repo, {"boom": boom}, clock, max_attempts=3)
    for _ in range(3):
        worker.run_until_idle()
        clock.advance(RETRY_DELAYS[-1])
    assert len(calls) == 3
    assert repo.retry_job(job_id)
    worker.run_until_idle()
    assert len(calls) > 3, "the retry button must run the job, not fail it unseen"


def test_enqueue_once_skips_a_waiting_duplicate(repo: SqliteRepository) -> None:
    assert repo.enqueue_once("geocode") is not None
    assert repo.enqueue_once("geocode") is None


# --- B24: long jobs run on a lane of their own ---------------------------------------------------


def test_a_long_job_does_not_starve_quick_ones(tmp_path: Path) -> None:
    """A backup (minutes to hours) must not hold up previews and uploads behind it."""
    repo = SqliteRepository(Database.open(tmp_path / "library.db"))
    backup_started, finish_backup = threading.Event(), threading.Event()
    previews: list[object] = []

    def long_backup(payload: dict[str, object]) -> None:
        backup_started.set()
        finish_backup.wait(10)

    repo.enqueue("backup_run", {})
    repo.enqueue("preview", {"asset_id": 1})
    lanes = Lanes(
        repo,
        {"backup_run": long_backup, "preview": lambda p: previews.append(p["asset_id"])},
        FakeClock(),
        long_kinds={"backup_run"},
        poll_seconds=0.01,
    )
    lanes.start()
    try:
        assert backup_started.wait(5)
        deadline = threading.Event()
        for _ in range(200):
            if previews:
                break
            deadline.wait(0.01)
        assert previews == [1], "the preview ran while the backup was still running"
    finally:
        finish_backup.set()
        lanes.stop()
    assert {j["kind"] for j in repo.list_jobs("done")} == {"backup_run", "preview"}
    assert lanes.kinds == {"backup_run", "preview"}


def test_run_until_idle_drains_every_lane(repo: SqliteRepository) -> None:
    done: list[str] = []
    repo.enqueue("backup_run", {})
    repo.enqueue("preview", {})
    lanes = Lanes(
        repo,
        {"backup_run": lambda p: done.append("backup"), "preview": lambda p: done.append("p")},
        FakeClock(),
        long_kinds={"backup_run"},
    )
    assert lanes.run_until_idle() == 2
    assert sorted(done) == ["backup", "p"]


def test_run_until_idle_can_be_limited_to_some_job_kinds(repo: SqliteRepository) -> None:
    done: list[str] = []
    for kind in ("backup_run", "preview", "geocode", "preview"):
        repo.enqueue(kind, {})
    lanes = Lanes(
        repo,
        {k: (lambda p, k=k: done.append(k)) for k in ("backup_run", "preview", "geocode")},  # type: ignore[misc]
        FakeClock(),
        long_kinds={"backup_run"},
        pooled={"preview": 2},
    )
    assert lanes.run_until_idle(only={"preview", "geocode"}) == 3
    assert done == ["preview", "geocode", "preview"]
    assert [j["kind"] for j in repo.list_jobs("queued")] == ["backup_run"]


def test_previews_run_on_a_pool_of_threads(tmp_path: Path) -> None:
    """C28: previews in parallel (max(1, cores - 2) threads); two meet at a barrier."""
    repo = SqliteRepository(Database.open(tmp_path / "library.db"))
    together = threading.Barrier(2, timeout=5)
    met: list[int] = []

    def preview(payload: dict[str, object]) -> None:
        together.wait()  # only passes if both previews run at the same time
        met.append(int(str(payload["asset_id"])))

    repo.enqueue("preview", {"asset_id": 1})
    repo.enqueue("preview", {"asset_id": 2})
    lanes = Lanes(
        repo,
        {"preview": preview},
        FakeClock(),
        long_kinds=set(),
        pooled={"preview": 2},
        poll_seconds=0.01,
    )
    lanes.start()
    try:
        for _ in range(500):
            if len(repo.list_jobs("done")) == 2:
                break
            threading.Event().wait(0.01)
    finally:
        lanes.stop()
    assert sorted(met) == [1, 2]
    assert len(repo.list_jobs("done")) == 2


# --- retries wait, longer each time ------------------------------------------------------------


def _waits(repo: SqliteRepository) -> list[object]:
    return [job["run_after"] for job in repo.list_jobs("queued")]


def test_a_failed_job_waits_a_minute_then_five_before_its_next_attempts(
    repo: SqliteRepository,
) -> None:
    """A network blip or an unplugged disk gets time to pass before the attempts are used up."""
    calls: list[datetime] = []
    clock = FakeClock()

    def offline(payload: dict[str, object]) -> None:
        calls.append(clock.now())
        raise ConnectionError("offline")

    repo.enqueue("pull", {})
    worker = Worker(repo, {"pull": offline}, clock, max_attempts=3)

    assert worker.run_until_idle() == 1
    assert _waits(repo) == [(NOW + timedelta(minutes=1)).isoformat()]
    clock.advance(timedelta(seconds=59))
    assert worker.run_until_idle() == 0, "not before its time"
    clock.advance(timedelta(seconds=1))
    assert worker.run_until_idle() == 1
    assert _waits(repo) == [(NOW + timedelta(minutes=6)).isoformat()], "5 minutes after the 2nd"
    clock.advance(timedelta(minutes=5))
    assert worker.run_until_idle() == 1
    assert calls == [NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=6)]
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 3 and failed["run_after"] is None


def test_with_more_attempts_allowed_the_third_retry_waits_25_minutes(
    repo: SqliteRepository,
) -> None:
    clock = FakeClock()

    def offline(payload: dict[str, object]) -> None:
        raise ConnectionError("offline")

    repo.enqueue("pull", {})
    worker = Worker(repo, {"pull": offline}, clock, max_attempts=4)
    delays = []
    for _ in range(3):
        worker.run_until_idle()
        (job,) = repo.list_jobs("queued")
        until = datetime.fromisoformat(str(job["run_after"]))
        delays.append(until - clock.now())
        clock.current = until
    assert delays == [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=25)]
    assert delays == list(RETRY_DELAYS)


def test_an_error_retrying_cannot_fix_fails_at_once_without_waiting(
    repo: SqliteRepository,
) -> None:
    def gone(payload: dict[str, object]) -> None:
        raise DomainError("that folder no longer exists")

    repo.enqueue("scan", {})
    assert Worker(repo, {"scan": gone}, FakeClock()).run_until_idle() == 1
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 1 and failed["run_after"] is None


def test_a_job_retried_by_hand_runs_at_once(repo: SqliteRepository) -> None:
    calls: list[int] = []
    clock = FakeClock()

    def offline(payload: dict[str, object]) -> None:
        calls.append(1)
        raise ConnectionError("offline")

    job_id = repo.enqueue("pull", {})
    worker = Worker(repo, {"pull": offline}, clock, max_attempts=1)
    worker.run_until_idle()
    assert repo.retry_job(job_id)
    assert worker.run_until_idle() == 1, "no waiting after the retry button"
    assert len(calls) == 2


def test_run_until_idle_returns_when_only_waiting_retries_are_left(
    repo: SqliteRepository,
) -> None:
    done: list[object] = []

    def offline(payload: dict[str, object]) -> None:
        raise ConnectionError("offline")

    repo.enqueue("pull", {})
    repo.enqueue("preview", {"asset_id": 1})
    lanes = Lanes(repo, {"pull": offline, "preview": done.append}, FakeClock(), long_kinds={"pull"})
    assert lanes.run_until_idle() == 2, "each ran once; the retry is left for later"
    assert done == [{"asset_id": 1}]
    assert [(j["kind"], j["attempts"]) for j in repo.list_jobs("queued")] == [("pull", 1)]
    assert lanes.run_until_idle(only={"pull"}) == 0


# --- every process owns the jobs it runs -------------------------------------------------------


def _claims(repo: SqliteRepository) -> list[tuple[object, ...]]:
    rows = repo._conn.execute("SELECT status, claimed_by, claimed_at FROM job ORDER BY id")
    return [tuple(row) for row in rows]


def test_owner_ids_name_the_process_and_differ_every_time() -> None:
    first, second = new_owner_id("server"), new_owner_id("server")
    assert first.startswith("server-") and second.startswith("server-")
    assert first != second
    assert new_owner_id("cli").startswith("cli-")


def test_a_worker_claims_jobs_under_its_owner_id(repo: SqliteRepository) -> None:
    seen: list[list[tuple[object, ...]]] = []
    repo.enqueue("echo", {})
    worker = Worker(repo, {"echo": lambda _: seen.append(_claims(repo))}, FakeClock(), owner="a")
    worker.run_until_idle()
    assert seen == [[("running", "a", NOW.isoformat())]]


def test_every_lane_of_a_process_shares_its_owner_id(repo: SqliteRepository) -> None:
    owners: list[object] = []

    def note(payload: dict[str, object]) -> None:
        owners.extend(owner for status, owner, _ in _claims(repo) if status == "running")

    for kind in ("backup_run", "preview", "geocode"):
        repo.enqueue(kind, {})
    lanes = Lanes(
        repo,
        {"backup_run": note, "preview": note, "geocode": note},
        FakeClock(),
        long_kinds={"backup_run"},
        pooled={"preview": 2},
        owner="server-1",
    )
    lanes.run_until_idle()
    assert owners == ["server-1"] * 3


def test_a_long_job_stays_fresh_while_its_process_is_alive(tmp_path: Path) -> None:
    """A backup of several hours: the heartbeat renews the claim, so another process that
    looks for stale jobs meanwhile leaves it alone."""
    db = tmp_path / "library.db"
    repo, other = SqliteRepository(Database.open(db)), SqliteRepository(Database.open(db))
    clock = FakeClock()
    sweep = StaleJobSweep(other, clock)
    requeued: list[int] = []

    def long_backup(payload: dict[str, object]) -> None:
        clock.advance(timedelta(hours=3))
        renewed = threading.Event()
        for _ in range(1000):  # until the heartbeat thread has renewed the claim
            if _claims(other) == [("running", "server-1", clock.now().isoformat())]:
                break
            renewed.wait(0.005)
        requeued.append(sweep.run())

    repo.enqueue("backup_run", {})
    worker = Worker(
        repo, {"backup_run": long_backup}, clock, owner="server-1", heartbeat_seconds=0.005
    )
    assert worker.run_until_idle() == 1
    assert requeued == [0], "the running backup was not handed to someone else"
    assert [j["attempts"] for j in repo.list_jobs("done")] == [1]


def test_the_heartbeat_stops_with_the_job(repo: SqliteRepository) -> None:
    before = threading.active_count()
    repo.enqueue("echo", {})
    Worker(repo, {"echo": lambda _: None}, FakeClock(), heartbeat_seconds=0.005).run_until_idle()
    assert threading.active_count() == before


def test_a_killed_process_s_job_is_taken_over_once_its_claim_is_stale(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    cli, server = SqliteRepository(Database.open(db)), SqliteRepository(Database.open(db))
    clock = FakeClock()
    ran: list[object] = []
    cli.enqueue("preview", {"asset_id": 1})
    assert cli.claim_next_job(clock.now(), owner="cli-1") is not None  # … and it is killed

    sweep = StaleJobSweep(server, clock)
    worker = Worker(server, {"preview": ran.append}, clock, owner="server-1")
    assert sweep.run() == 0 and worker.run_until_idle() == 0, "it may still be alive"
    clock.advance(STALE_SWEEP_INTERVAL)
    assert sweep.run() == 0, "one missed minute is not a dead process"
    for _ in range(5):
        clock.advance(STALE_SWEEP_INTERVAL)
        sweep.run()
    assert clock.now() - NOW > CLAIM_STALE_AFTER
    assert worker.run_until_idle() == 1
    assert ran == [{"asset_id": 1}]
    assert [j["attempts"] for j in server.list_jobs("done")] == [2]


def test_a_job_that_kills_every_process_running_it_fails_for_good(tmp_path: Path) -> None:
    """The crash-loop guard with leases: each run that died counts as an attempt."""
    db = tmp_path / "library.db"
    repo, server = SqliteRepository(Database.open(db)), SqliteRepository(Database.open(db))
    clock = FakeClock()
    ran: list[object] = []
    repo.enqueue("crashy", {})
    sweep = StaleJobSweep(server, clock)
    for n in range(3):
        assert repo.claim_next_job(clock.now(), owner=f"cli-{n}") is not None  # … killed
        clock.advance(CLAIM_STALE_AFTER + timedelta(seconds=1))
        assert StaleJobSweep(server, clock).run() == 1
    worker = Worker(server, {"crashy": ran.append}, clock, max_attempts=3, owner="server-1")
    assert worker.run_until_idle() == 1
    assert ran == [] and sweep.run() == 0
    (failed,) = server.list_jobs("failed")
    assert "3 attempts" in str(failed["error"])


def test_after_the_machine_slept_live_processes_get_time_to_renew_their_claims(
    repo: SqliteRepository,
) -> None:
    """A laptop that slept for hours: every claim looks old, also a running backup's of this
    very process. The first look after waking changes nothing; heartbeats come first."""
    clock = FakeClock()
    sweep = StaleJobSweep(repo, clock)
    job_id = repo.enqueue("backup_run", {})
    repo.claim_next_job(clock.now(), owner="server-1")
    assert sweep.run() == 0
    clock.advance(timedelta(hours=8))  # lid closed

    assert sweep.run() == 0, "this process stood still: old claims prove nothing"
    repo.renew_claim(job_id, "server-1", clock.now())  # the heartbeat, within 30 s of waking
    clock.advance(STALE_SWEEP_INTERVAL)
    assert sweep.run() == 0
    assert _claims(repo)[0][0] == "running"


def test_after_a_sleep_a_job_whose_process_is_really_gone_is_still_requeued(
    repo: SqliteRepository,
) -> None:
    clock = FakeClock()
    sweep = StaleJobSweep(repo, clock)
    repo.enqueue("preview", {})
    repo.claim_next_job(clock.now(), owner="cli-dead")
    sweep.run()
    clock.advance(timedelta(hours=8))
    assert sweep.run() == 0
    clock.advance(STALE_SWEEP_INTERVAL)
    assert sweep.run() == 1
