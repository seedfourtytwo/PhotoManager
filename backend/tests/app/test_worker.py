import threading
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import Blake3Hasher, DiskLibraryStore
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.app.derivatives import GeneratePreview
from photo_assistant.app.worker import Worker
from tests.factories import NOW, new_asset


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture
def repo() -> SqliteRepository:
    return SqliteRepository(open_database(":memory:"))


def test_worker_runs_jobs_until_idle(repo: SqliteRepository) -> None:
    done: list[object] = []
    repo.enqueue("echo", {"n": 1})
    repo.enqueue("echo", {"n": 2})
    worker = Worker(repo, {"echo": lambda payload: done.append(payload["n"])}, FixedClock())
    assert worker.run_until_idle() == 2
    assert done == [1, 2]
    assert len(repo.list_jobs("done")) == 2


def test_failing_job_is_retried_then_marked_failed_with_reason(repo: SqliteRepository) -> None:
    def boom(payload: dict[str, object]) -> None:
        raise ValueError("decoder exploded")

    repo.enqueue("boom", {})
    worker = Worker(repo, {"boom": boom}, FixedClock(), max_attempts=3)
    worker.run_until_idle()
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 3
    assert "decoder exploded" in str(failed["error"])


def test_unknown_job_kind_fails_immediately(repo: SqliteRepository) -> None:
    repo.enqueue("mystery", {})
    Worker(repo, {}, FixedClock()).run_until_idle()
    (failed,) = repo.list_jobs("failed")
    assert failed["attempts"] == 1 and "no handler" in str(failed["error"])


def test_background_thread_starts_and_stops_cleanly(repo: SqliteRepository) -> None:
    ran = threading.Event()
    repo.enqueue("ping", {})
    worker = Worker(repo, {"ping": lambda _: ran.set()}, FixedClock(), poll_seconds=0.01)
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


def test_preview_for_a_missing_asset_is_an_error(repo: SqliteRepository, tmp_path: Path) -> None:
    job = GeneratePreview(repo, DiskLibraryStore(tmp_path), VipsRenderer())
    with pytest.raises(LookupError, match="no asset"):
        job({"asset_id": 42})


def test_busy_library_requeues_without_using_up_attempts(repo: SqliteRepository) -> None:
    from photo_assistant.ports import ImportBusyError

    calls = []

    def busy(payload: dict[str, object]) -> None:
        calls.append(1)
        if len(calls) < 5:
            raise ImportBusyError("an import into this library is already running")

    repo.enqueue("scan", {})
    worker = Worker(repo, {"scan": busy}, FixedClock(), max_attempts=3)
    for _ in range(5):
        worker.run_once()
    assert repo.list_jobs("done"), "succeeded on the 5th try although max_attempts is 3"


def test_a_job_that_keeps_killing_the_process_is_given_up_on(repo: SqliteRepository) -> None:
    """A segfault or OOM never reaches the worker's except branch: only the claims count."""
    ran: list[object] = []
    repo.enqueue("crashy", {})
    for _ in range(3):  # three starts: claimed, the process dies, the next start requeues it
        assert repo.claim_next_job(NOW) is not None
        assert repo.recover_interrupted_jobs() == 1
    worker = Worker(repo, {"crashy": ran.append}, FixedClock(), max_attempts=3)
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
        repo.recover_interrupted_jobs()
    Worker(repo, {"flaky": ran.append}, FixedClock(), max_attempts=3).run_until_idle()
    assert ran == [{}] and len(repo.list_jobs("done")) == 1


def test_a_failed_job_retried_by_hand_runs_again(repo: SqliteRepository) -> None:
    calls: list[int] = []

    def boom(payload: dict[str, object]) -> None:
        calls.append(1)
        raise ValueError("decoder exploded")

    job_id = repo.enqueue("boom", {})
    worker = Worker(repo, {"boom": boom}, FixedClock(), max_attempts=3)
    worker.run_until_idle()
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
    from photo_assistant.app.worker import Lanes

    repo = SqliteRepository(open_database(tmp_path / "library.db"))
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
        FixedClock(),
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
    from photo_assistant.app.worker import Lanes

    done: list[str] = []
    repo.enqueue("backup_run", {})
    repo.enqueue("preview", {})
    lanes = Lanes(
        repo,
        {"backup_run": lambda p: done.append("backup"), "preview": lambda p: done.append("p")},
        FixedClock(),
        long_kinds={"backup_run"},
    )
    assert lanes.run_until_idle() == 2
    assert sorted(done) == ["backup", "p"]


def test_previews_run_on_a_pool_of_threads(tmp_path: Path) -> None:
    """C28: previews in parallel (max(1, cores - 2) threads); two meet at a barrier."""
    from photo_assistant.app.worker import Lanes

    repo = SqliteRepository(open_database(tmp_path / "library.db"))
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
        FixedClock(),
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
