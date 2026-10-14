"""Exposure settings for photos imported before they were kept: read from the library copy,
in batches, each batch a job of its own, so it can be cut off and started again."""

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.exposure_backfill import EXPOSURE_BACKFILL_JOB, BackfillExposure
from photo_assistant.app.worker import Worker
from photo_assistant.domain.exposure import Exposure
from photo_assistant.domain.job_queue import RETRY_DELAYS
from photo_assistant.domain.model import PhotoMetadata
from tests.factories import NOW, new_asset
from tests.fakes import FakeClock

ROOT = Path("/library")


def shot(n: int) -> Exposure:
    return Exposure(f_number=2.8, exposure_time=1 / 250, iso=100 * n, focal_length=35.0)


class FakeReader:
    """Answers from a table by file name; a file it does not know has no exposure tags."""

    def __init__(self, known: dict[str, Exposure]) -> None:
        self.known = known
        self.batches: list[list[str]] = []
        self.fail_next = False

    def read_many(self, paths: Sequence[Path]) -> list[PhotoMetadata]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("exiftool went away")
        assert all(path.is_relative_to(ROOT) for path in paths), "only ever the library copy"
        self.batches.append([path.name for path in paths])
        return [PhotoMetadata(exposure=self.known.get(path.name, Exposure())) for path in paths]


def library(repo: SqliteRepository, count: int) -> tuple[list[int], FakeReader]:
    """``count`` photos stored without exposure; the reader knows one for each."""
    ids = [repo.add_asset(new_asset(n), NOW) for n in range(1, count + 1)]
    return ids, FakeReader({f"{n:064x}.jpg": shot(n) for n in range(1, count + 1)})


def worker_for(
    repo: SqliteRepository, reader: FakeReader, clock: FakeClock, batch: int = 2
) -> Worker:
    handler = BackfillExposure(repo, reader, lambda relative: ROOT / relative, batch=batch)
    return Worker(repo, {EXPOSURE_BACKFILL_JOB: handler}, clock)


def exposures(repo: SqliteRepository, ids: list[int]) -> list[Exposure]:
    return [asset.exposure for i in ids if (asset := repo.get_asset(i)) is not None]


def test_the_backfill_fills_every_photo_that_has_no_exposure_yet(
    repo: SqliteRepository, clock: FakeClock
) -> None:
    ids, reader = library(repo, 5)
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    worker_for(repo, reader, clock).run_until_idle()
    assert exposures(repo, ids) == [shot(n) for n in range(1, 6)]
    assert repo.list_jobs("queued") == [] and repo.list_jobs("failed") == []


def test_each_batch_is_a_job_of_its_own_that_queues_the_next(
    repo: SqliteRepository, clock: FakeClock
) -> None:
    ids, reader = library(repo, 5)
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    worker = worker_for(repo, reader, clock)
    assert worker.run_once()
    assert exposures(repo, ids) == [shot(1), shot(2), Exposure(), Exposure(), Exposure()]
    (waiting,) = repo.list_jobs("queued")
    assert (waiting["kind"], waiting["payload"]) == (EXPOSURE_BACKFILL_JOB, {"after": ids[1]})
    assert worker.run_until_idle() == 2
    assert [len(batch) for batch in reader.batches] == [2, 2, 1]


def test_a_batch_that_failed_is_tried_again_and_earlier_batches_are_not_read_twice(
    repo: SqliteRepository, clock: FakeClock
) -> None:
    ids, reader = library(repo, 5)
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    worker = worker_for(repo, reader, clock)
    assert worker.run_once()
    reader.fail_next = True
    worker.run_until_idle()
    assert exposures(repo, ids)[2:] == [Exposure()] * 3, "cut off: nothing half-written"
    clock.advance(RETRY_DELAYS[0] + timedelta(seconds=1))
    worker.run_until_idle()
    assert exposures(repo, ids) == [shot(n) for n in range(1, 6)]
    read = [name for batch in reader.batches for name in batch]
    assert len(read) == len(set(read)) == 5


def test_a_batch_cut_off_after_it_was_stored_is_safe_to_run_again(
    repo: SqliteRepository, clock: FakeClock
) -> None:
    """The process died between storing a batch and queueing the next: the job is queued
    again (the stale-claim sweep) and runs with the same starting point."""
    ids, reader = library(repo, 4)
    handler = BackfillExposure(repo, reader, lambda relative: ROOT / relative, batch=2)
    handler({})
    for job in repo.list_jobs("queued"):  # as if the follow-up had never been queued
        repo.fail_job(int(str(job["id"])), "lost", retry=False, now=NOW)
    handler({})
    worker_for(repo, reader, clock).run_until_idle()
    assert exposures(repo, ids) == [shot(n) for n in range(1, 5)]


def test_running_it_a_second_time_reads_only_photos_still_without_values_and_changes_nothing(
    repo: SqliteRepository, clock: FakeClock
) -> None:
    ids, reader = library(repo, 3)
    del reader.known[f"{2:064x}.jpg"]  # a scan: no exposure tags
    worker = worker_for(repo, reader, clock, batch=10)
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    worker.run_until_idle()
    first = exposures(repo, ids)
    assert first == [shot(1), Exposure(), shot(3)]
    reader.known = {}  # whatever the files say now, stored values stay
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    worker.run_until_idle()
    assert exposures(repo, ids) == first
    assert reader.batches[1] == [f"{2:064x}.jpg"]


def test_starting_it_while_one_waits_queues_no_second_one(repo: SqliteRepository) -> None:
    assert repo.enqueue_once(EXPOSURE_BACKFILL_JOB) is not None
    assert repo.enqueue_once(EXPOSURE_BACKFILL_JOB) is None
    assert len(repo.list_jobs("queued")) == 1


def test_an_empty_library_finishes_at_once(repo: SqliteRepository, clock: FakeClock) -> None:
    reader = FakeReader({})
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    assert worker_for(repo, reader, clock).run_until_idle() == 1
    assert reader.batches == [] and repo.list_jobs("queued") == []


def test_a_file_that_cannot_be_read_is_left_empty_and_the_rest_is_filled(
    repo: SqliteRepository, clock: FakeClock
) -> None:
    ids, reader = library(repo, 3)

    def read_many(paths: Sequence[Path]) -> list[PhotoMetadata]:
        gone = f"{2:064x}.jpg"
        return [
            PhotoMetadata(error="unreadable by exiftool")
            if path.name == gone
            else PhotoMetadata(exposure=reader.known[path.name])
            for path in paths
        ]

    reader.read_many = read_many  # type: ignore[method-assign]
    repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    worker_for(repo, reader, clock, batch=10).run_until_idle()
    assert exposures(repo, ids) == [shot(1), Exposure(), shot(3)]
    assert repo.list_jobs("failed") == []
