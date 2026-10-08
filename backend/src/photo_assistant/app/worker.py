"""A small job worker: the queue lives in the database, so it survives restarts."""

import logging
import threading
from collections.abc import Callable, Collection, Mapping

from photo_assistant.domain.errors import DomainError
from photo_assistant.ports import Clock, ImportBusyError, Repository

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, object]], object]


class Worker:
    def __init__(
        self,
        repo: Repository,
        handlers: Mapping[str, Handler],
        clock: Clock,
        *,
        max_attempts: int = 3,
        poll_seconds: float = 1.0,
        only: Collection[str] | None = None,
        excluding: Collection[str] = (),
        name: str = "pa-worker",
    ) -> None:
        self._repo = repo
        self._handlers = dict(handlers)
        self._clock = clock
        self._max_attempts = max_attempts
        self._poll = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._only = None if only is None else frozenset(only)  # this lane's job kinds
        self._excluding = frozenset(excluding)
        self._name = name

    @property
    def kinds(self) -> set[str]:
        """The job kinds this worker can run."""
        return set(self._handlers)

    def run_once(self) -> bool:
        """Process one job. Returns False when the queue is empty."""
        job = self._repo.claim_next_job(
            self._clock.now(), only=self._only, excluding=self._excluding
        )
        if job is None:
            return False
        handler = self._handlers.get(job.kind)
        if handler is None:
            self._repo.fail_job(job.id, f"no handler for job kind '{job.kind}'", retry=False)
            return True
        if job.attempts > self._max_attempts:
            # Only reachable when earlier runs never came back (the process was killed by a
            # crash or the OOM killer and the next start requeued the job): stop the loop.
            log.warning("job given up on", extra={"job_id": job.id, "kind": job.kind})
            reason = f"never finished (did it crash the server?): gave up after {job.attempts - 1}"
            self._repo.fail_job(job.id, f"{reason} attempts", retry=False)
            return True
        try:
            handler(job.payload)
        except ImportBusyError:
            # Another import holds the library; try again later without using up attempts.
            self._repo.release_job(job.id)
            return False
        except DomainError as exc:
            # not transient (a folder is gone, a value is invalid): retrying changes nothing
            log.warning("job failed", extra={"job_id": job.id, "kind": job.kind, "retry": False})
            self._repo.fail_job(job.id, f"{type(exc).__name__}: {exc}", retry=False)
        except Exception as exc:
            retry = job.attempts < self._max_attempts
            log.warning("job failed", extra={"job_id": job.id, "kind": job.kind, "retry": retry})
            self._repo.fail_job(job.id, f"{type(exc).__name__}: {exc}", retry=retry)
        else:
            self._repo.complete_job(job.id)
        return True

    def run_until_idle(self) -> int:
        count = 0
        while self.run_once():
            count += 1
        return count

    # --- background thread -----------------------------------------------------------------

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                busy = self.run_once()
            except Exception:
                log.exception("worker loop error")
                busy = False
            if not busy:
                self._stop.wait(self._poll)


class Lanes:
    """Two workers on one queue (B24): long jobs (backups, restore tests, source scans with
    rclone pulls) on a lane of their own, so previews and uploads never wait behind them."""

    def __init__(
        self,
        repo: Repository,
        handlers: Mapping[str, Handler],
        clock: Clock,
        *,
        long_kinds: Collection[str],
        pooled: Mapping[str, int] | None = None,
        poll_seconds: float = 1.0,
    ) -> None:
        """``pooled``: job kinds that get a pool of threads of their own, e.g. previews with
        max(1, cores - 2) threads (C28)."""
        self._repo, self._handlers, self._clock = repo, dict(handlers), clock
        self.long_kinds = frozenset(long_kinds)
        pools = dict(pooled or {})
        own = self.long_kinds | set(pools)
        quick = {k: h for k, h in handlers.items() if k not in own}
        slow = {k: h for k, h in handlers.items() if k in self.long_kinds}
        self.quick = Worker(repo, quick, clock, poll_seconds=poll_seconds, excluding=own)
        self.long = Worker(
            repo, slow, clock, poll_seconds=poll_seconds, only=self.long_kinds, name="pa-long-jobs"
        )
        self.pool = [
            Worker(
                repo,
                {kind: handlers[kind]},
                clock,
                poll_seconds=poll_seconds,
                only={kind},
                name=f"pa-{kind}-{n}",
            )
            for kind, size in pools.items()
            if kind in handlers
            for n in range(max(1, size))
        ]

    @property
    def _workers(self) -> list[Worker]:
        return [self.quick, self.long, *self.pool]

    @property
    def kinds(self) -> set[str]:
        return set().union(*(w.kinds for w in self._workers))

    def run_until_idle(self, only: Collection[str] | None = None) -> int:
        """Every lane, until none finds a job (follow-ups may cross lanes). ``only``: just
        these job kinds, for a caller that must leave the rest of the queue to the server."""
        if only is not None:
            mine = {kind: h for kind, h in self._handlers.items() if kind in only}
            return Worker(self._repo, mine, self._clock, only=only).run_until_idle()
        total = 0
        while ran := sum(w.run_until_idle() for w in self._workers):
            total += ran
        return total

    def start(self) -> None:
        for worker in self._workers:
            worker.start()

    def stop(self, timeout: float = 10.0) -> None:
        for worker in self._workers:
            worker.stop(timeout)

    @property
    def is_running(self) -> bool:
        return any(w.is_running for w in self._workers)
