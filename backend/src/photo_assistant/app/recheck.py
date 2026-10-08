"""ScheduledChecks: sources that check themselves again on a timer (issues 7 and 8).

Nothing here reads a folder or a cloud account: it only queues the ordinary "scan source" job
for each source whose time has come, the same job "Check again" queues by hand.
"""

from datetime import datetime
from typing import Protocol

from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.domain.model import Source
from photo_assistant.domain.recheck import is_due, next_check_at
from photo_assistant.ports import Clock


class CheckStore(Protocol):
    def list_sources(self) -> list[Source]: ...

    def last_check_attempts(self, job_kind: str) -> dict[int, datetime]:
        """Source id → when its latest check started, whether it worked or not."""
        ...

    def sources_being_checked(self, job_kind: str) -> set[int]:
        """Sources with a check waiting or running."""
        ...

    def enqueue(self, kind: str, payload: dict[str, object]) -> int: ...


class ScheduledChecks:
    def __init__(self, store: CheckStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def queue_due(self) -> list[int]:
        """Queue a check for every source that is due and has none waiting or running;
        returns their ids. Called by one periodic thread, so two looks never overlap."""
        now = self._clock.now()
        attempts = self._store.last_check_attempts(SCAN_JOB_KIND)
        busy = self._store.sources_being_checked(SCAN_JOB_KIND)
        due = [
            s.id
            for s in self._store.list_sources()
            if s.id not in busy and is_due(s.recheck, s.enabled, attempts.get(s.id), now)
        ]
        for source_id in due:
            self._store.enqueue(SCAN_JOB_KIND, {"source_id": source_id})
        return due

    def next_checks(self) -> dict[int, datetime | None]:
        """Source id → when it next checks itself (None: never, it is off or disabled)."""
        now = self._clock.now()
        attempts = self._store.last_check_attempts(SCAN_JOB_KIND)
        return {
            s.id: next_check_at(s.recheck, s.enabled, attempts.get(s.id), now)
            for s in self._store.list_sources()
        }
