"""A small job worker: the queue lives in the database, so it survives restarts.

The server and CLI commands share that queue. Every process claims jobs under an owner id of
its own and renews the claim while a job runs (a heartbeat); a claim nobody renews any more
belongs to a process that died, and ``StaleJobSweep`` queues its job again.
"""

import logging
import os
import threading
import uuid
from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta

from photo_assistant.domain.errors import DomainError
from photo_assistant.domain.job_queue import (
    CLAIM_STALE_AFTER,
    HEARTBEAT_INTERVAL,
    STALE_SWEEP_INTERVAL,
    retry_delay,
)
from photo_assistant.ports import Clock, ImportBusyError, Repository

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, object]], object]


def new_owner_id(role: str) -> str:
    """The name a process claims jobs under, e.g. ``server-4711-9f2c61d0``: what it is, its
    process id (to find it with ``ps``) and a random part, new at every start."""
    return f"{role}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


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
        owner: str | None = None,
        heartbeat_seconds: float = HEARTBEAT_INTERVAL.total_seconds(),
    ) -> None:
        """``owner``: the process's id for its claims (every lane of a process shares it)."""
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
        self._owner = owner or new_owner_id("worker")
        self._heartbeat = heartbeat_seconds

    @property
    def kinds(self) -> set[str]:
        """The job kinds this worker can run."""
        return set(self._handlers)

    def run_once(self) -> bool:
        """Process one job. Returns False when no job is due: the queue is empty, or what is
        left waits for its retry time."""
        job = self._repo.claim_next_job(
            self._clock.now(), owner=self._owner, only=self._only, excluding=self._excluding
        )
        if job is None:
            return False
        handler = self._handlers.get(job.kind)
        if handler is None:
            self._repo.fail_job(job.id, f"no handler for job kind '{job.kind}'", retry=False)
            return True
        if job.attempts > self._max_attempts:
            # Only reachable when earlier runs never came back (the process was killed by a
            # crash or the OOM killer and its stale claim was requeued): stop the loop.
            log.warning("job given up on", extra={"job_id": job.id, "kind": job.kind})
            reason = f"never finished (did it crash the server?): gave up after {job.attempts - 1}"
            self._repo.fail_job(job.id, f"{reason} attempts", retry=False)
            return True
        try:
            with self._renewing_claim(job.id):
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
            # what failed may pass (network, a locked repository, an unplugged disk): wait
            run_after = self._clock.now() + retry_delay(job.attempts) if retry else None
            self._repo.fail_job(job.id, f"{type(exc).__name__}: {exc}", retry, run_after)
        else:
            self._repo.complete_job(job.id)
        return True

    @contextmanager
    def _renewing_claim(self, job_id: int) -> Iterator[None]:
        """Heartbeat while a job runs, on a thread of its own, so a job of any length keeps
        its claim fresh for as long as this process is alive."""
        finished = threading.Event()

        def renew() -> None:
            while not finished.wait(self._heartbeat):
                try:
                    self._repo.renew_claim(job_id, self._owner, self._clock.now())
                except Exception:  # a busy database: the next heartbeat tries again
                    log.exception("job claim not renewed", extra={"job_id": job_id})

        heartbeat = threading.Thread(target=renew, name=f"{self._name}-heartbeat", daemon=True)
        heartbeat.start()
        try:
            yield
        finally:
            finished.set()
            heartbeat.join()

    def run_until_idle(self) -> int:
        """Run every job that is due, then return (the CLI and tests use this).

        "Idle" means nothing is due *now*: a failed job waiting for its retry time is left in
        the queue, neither waited for nor spun on. The server's worker picks it up when its
        time comes; a caller that needs it sooner calls again later."""
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
        owner: str | None = None,
    ) -> None:
        """``pooled``: job kinds that get a pool of threads of their own, e.g. previews with
        max(1, cores - 2) threads (C28). ``owner``: this process's id for its claims."""
        self._repo, self._handlers, self._clock = repo, dict(handlers), clock
        self._owner = owner or new_owner_id("worker")
        self.long_kinds = frozenset(long_kinds)
        pools = dict(pooled or {})
        own = self.long_kinds | set(pools)
        quick = {k: h for k, h in handlers.items() if k not in own}
        slow = {k: h for k, h in handlers.items() if k in self.long_kinds}
        self.quick = Worker(
            repo, quick, clock, poll_seconds=poll_seconds, excluding=own, owner=self._owner
        )
        self.long = Worker(
            repo,
            slow,
            clock,
            poll_seconds=poll_seconds,
            only=self.long_kinds,
            name="pa-long-jobs",
            owner=self._owner,
        )
        self.pool = [
            Worker(
                repo,
                {kind: handlers[kind]},
                clock,
                poll_seconds=poll_seconds,
                only={kind},
                name=f"pa-{kind}-{n}",
                owner=self._owner,
            )
            for kind, size in pools.items()
            if kind in handlers
            for n in range(max(1, size))
        ]

    @property
    def owner(self) -> str:
        """The id this process claims jobs under."""
        return self._owner

    @property
    def _workers(self) -> list[Worker]:
        return [self.quick, self.long, *self.pool]

    @property
    def kinds(self) -> set[str]:
        return set().union(*(w.kinds for w in self._workers))

    def run_until_idle(self, only: Collection[str] | None = None) -> int:
        """Every lane, until none finds a job that is due (follow-ups may cross lanes; retries
        waiting for their time stay queued, see ``Worker.run_until_idle``). ``only``: just
        these job kinds, for a caller that must leave the rest of the queue to the server."""
        if only is not None:
            mine = {kind: h for kind, h in self._handlers.items() if kind in only}
            worker = Worker(self._repo, mine, self._clock, only=only, owner=self._owner)
            return worker.run_until_idle()
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


class StaleJobSweep:
    """Queues jobs again whose process died while running them: nobody renews their claim.

    Run at server start and every ``STALE_SWEEP_INTERVAL``. A job with a fresh claim is left
    alone, whoever owns it, so a server start never restarts what a CLI command is running."""

    def __init__(
        self,
        repo: Repository,
        clock: Clock,
        *,
        stale_after: timedelta = CLAIM_STALE_AFTER,
        every: timedelta = STALE_SWEEP_INTERVAL,
    ) -> None:
        self._repo, self._clock = repo, clock
        self._stale_after, self._every = stale_after, every
        self._last_run: datetime | None = None

    def run(self) -> int:
        now = self._clock.now()
        last_run, self._last_run = self._last_run, now
        if last_run is not None and now - last_run > 2 * self._every:
            # This process stood still (the laptop slept, the clock was set): every claim
            # looks old, also those of live processes and of this one. Their heartbeats come
            # within HEARTBEAT_INTERVAL, sooner than the next sweep: decide then.
            return 0
        requeued = self._repo.requeue_stale_jobs(now - self._stale_after)
        if requeued:
            log.warning("requeued jobs whose process died", extra={"jobs": requeued})
        return requeued
