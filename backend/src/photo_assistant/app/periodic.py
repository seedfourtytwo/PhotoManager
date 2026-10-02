"""Periodic housekeeping next to the job worker: due backups, later the trash purge.

One background thread runs each task every ``every_seconds``; a task that raises is logged
and tried again next time, it never stops the others. Tasks run one after another, so a long
backup delays (never overlaps) the next check.
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PeriodicTask:
    name: str
    every_seconds: float
    run: Callable[[], object]


class Periodic:
    def __init__(
        self,
        tasks: Sequence[PeriodicTask],
        *,
        monotonic: Callable[[], float] = time.monotonic,
        tick_seconds: float = 5.0,
    ) -> None:
        self._tasks = list(tasks)
        self._monotonic = monotonic
        self._tick = tick_seconds
        self._next_at = {t.name: 0.0 for t in self._tasks}  # first tick runs everything
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def task_names(self) -> list[str]:
        """For inspection (the wiring test checks what the server schedules)."""
        return [t.name for t in self._tasks]

    def tick(self) -> list[str]:
        """Run every task whose time has come; returns their names."""
        ran = []
        for task in self._tasks:
            if self._monotonic() < self._next_at[task.name]:
                continue
            try:
                task.run()
            except Exception:
                log.exception("periodic task failed", extra={"task": task.name})
            self._next_at[task.name] = self._monotonic() + task.every_seconds
            ran.append(task.name)
        return ran

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="pa-periodic", daemon=True)
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
            self.tick()
            self._stop.wait(self._tick)
