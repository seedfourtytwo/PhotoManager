"""A small job worker: the queue lives in the database, so it survives restarts."""

import logging
import threading
from collections.abc import Callable, Mapping

from photo_assistant.ports import Clock, Repository

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
    ) -> None:
        self._repo = repo
        self._handlers = dict(handlers)
        self._clock = clock
        self._max_attempts = max_attempts
        self._poll = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Process one job. Returns False when the queue is empty."""
        job = self._repo.claim_next_job(self._clock.now())
        if job is None:
            return False
        handler = self._handlers.get(job.kind)
        if handler is None:
            self._repo.fail_job(job.id, f"no handler for job kind '{job.kind}'", retry=False)
            return True
        try:
            handler(job.payload)
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
        self._thread = threading.Thread(target=self._loop, name="pa-worker", daemon=True)
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
