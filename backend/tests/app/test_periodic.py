"""The periodic runner that calls BackupService.run_due (and later the trash purge)."""

import threading

import pytest

from photo_assistant.app.periodic import Periodic, PeriodicTask


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_runs_each_task_on_its_own_interval() -> None:
    clock = FakeTime()
    calls: list[str] = []
    periodic = Periodic(
        [
            PeriodicTask("backups", 60, lambda: calls.append("backups")),
            PeriodicTask("trash", 3600, lambda: calls.append("trash")),
        ],
        monotonic=clock,
    )
    assert periodic.tick() == ["backups", "trash"], "everything runs once at start"
    clock.now += 59
    assert periodic.tick() == []
    clock.now += 1
    assert periodic.tick() == ["backups"]
    clock.now += 3600
    assert periodic.tick() == ["backups", "trash"]
    assert calls == ["backups", "trash", "backups", "backups", "trash"]


def test_a_failing_task_is_logged_and_does_not_stop_the_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom() -> None:
        raise RuntimeError("restic exploded")

    ran: list[str] = []
    periodic = Periodic(
        [PeriodicTask("bad", 1, boom), PeriodicTask("good", 1, lambda: ran.append("good"))],
        monotonic=FakeTime(),
    )
    assert periodic.tick() == ["bad", "good"]
    assert ran == ["good"]
    assert "periodic task failed" in caplog.text


def test_background_thread_starts_and_stops() -> None:
    done = threading.Event()
    periodic = Periodic([PeriodicTask("x", 60, done.set)], tick_seconds=0.01)
    periodic.start()
    periodic.start()  # idempotent
    assert done.wait(2)
    assert periodic.is_running
    periodic.stop()
    assert not periodic.is_running
