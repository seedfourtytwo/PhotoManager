"""ScheduledChecks: queue a check for every source whose time has come, never twice."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from photo_assistant.app.recheck import ScheduledChecks
from photo_assistant.domain.model import Source
from photo_assistant.domain.recheck import Recheck
from tests.factories import NOW
from tests.fakes import FakeClock

HOUR = timedelta(hours=1)


@dataclass
class FakeStore:
    sources: list[Source]
    attempts: dict[int, datetime] = field(default_factory=dict)
    checking: set[int] = field(default_factory=set)
    queued: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def list_sources(self) -> list[Source]:
        return self.sources

    def last_check_attempts(self, job_kind: str) -> dict[int, datetime]:
        assert job_kind == "scan_source"
        return self.attempts

    def sources_being_checked(self, job_kind: str) -> set[int]:
        assert job_kind == "scan_source"
        return self.checking

    def enqueue(self, kind: str, payload: dict[str, object]) -> int:
        self.queued.append((kind, payload))
        self.checking.add(int(str(payload["source_id"])))
        return len(self.queued)


def _source(source_id: int, recheck: Recheck, *, enabled: bool = True) -> Source:
    return Source(source_id, f"s{source_id}", f"/s{source_id}", enabled, recheck=recheck)


def test_queues_one_scan_job_for_each_source_that_is_due() -> None:
    store = FakeStore(
        [
            _source(1, Recheck.HOURLY),  # checked two hours ago: due
            _source(2, Recheck.DAILY),  # checked two hours ago: not yet
            _source(3, Recheck.WEEKLY),  # never checked: due
            _source(4, Recheck.OFF),
            _source(5, Recheck.HOURLY, enabled=False),
        ],
        attempts={1: NOW - 2 * HOUR, 2: NOW - 2 * HOUR, 4: NOW - 900 * HOUR},
    )
    checks = ScheduledChecks(store, FakeClock())
    assert checks.queue_due() == [1, 3]
    assert store.queued == [("scan_source", {"source_id": 1}), ("scan_source", {"source_id": 3})]


def test_a_source_whose_check_is_waiting_or_running_is_not_queued_again() -> None:
    store = FakeStore([_source(1, Recheck.HOURLY), _source(2, Recheck.HOURLY)], checking={2})
    checks = ScheduledChecks(store, FakeClock())
    assert checks.queue_due() == [1]
    assert checks.queue_due() == [], "the first look's job is still waiting"
    assert len(store.queued) == 1


def test_next_checks_tells_when_each_source_checks_itself_next() -> None:
    store = FakeStore(
        [
            _source(1, Recheck.DAILY),
            _source(2, Recheck.OFF),
            _source(3, Recheck.HOURLY, enabled=False),
            _source(4, Recheck.WEEKLY),
        ],
        attempts={1: NOW - HOUR, 2: NOW, 3: NOW},
    )
    assert ScheduledChecks(store, FakeClock()).next_checks() == {
        1: NOW + 23 * HOUR,
        2: None,
        3: None,
        4: NOW,
    }
