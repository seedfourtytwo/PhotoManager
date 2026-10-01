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


def test_periodic_jobs_are_queued_once_per_interval(repo: SqliteRepository) -> None:
    worker = Worker(repo, {"tidy": lambda payload: None}, FixedClock(), periodic={"tidy": 3600})
    worker.enqueue_due(now=0.0)
    worker.enqueue_due(now=10.0)
    assert len(repo.list_jobs("queued")) == 1, "not due again yet"
    worker.enqueue_due(now=3601.0)
    assert len(repo.list_jobs("queued")) == 1, "never two of the same kind waiting"
    worker.run_until_idle()
    worker.enqueue_due(now=7300.0)
    assert len(repo.list_jobs("queued")) == 1


def test_enqueue_once_skips_a_waiting_duplicate(repo: SqliteRepository) -> None:
    assert repo.enqueue_once("geocode") is not None
    assert repo.enqueue_once("geocode") is None
