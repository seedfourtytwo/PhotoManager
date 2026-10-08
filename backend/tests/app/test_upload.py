"""UploadInbox and DeviceTokens with a real temp-folder spool and in-memory fakes."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.upload_spool import DiskUploadSpool
from photo_assistant.app.devices import DeviceTokens, hash_token
from photo_assistant.app.upload import UploadInbox, UploadOutcome, UploadSettings
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.model import Source
from photo_assistant.ports.upload import Device, SpooledUpload
from tests.fakes import FakeClock

ME = Viewer(7, Role.MEMBER)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"pixels" * 10


@dataclass
class FakeLibrary:
    known: dict[str, int] = field(default_factory=dict)
    jobs: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    runs: dict[int, tuple[str, datetime]] = field(default_factory=dict)  # newest per source

    def list_import_runs(
        self, source_id: int | None = None, limit: int = 200
    ) -> list[dict[str, object]]:
        if source_id not in self.runs:
            return []
        status, started = self.runs[source_id]
        return [{"status": status, "started_at": started.isoformat()}]

    def hashes_present(self, viewer: Viewer, hashes: Sequence[str]) -> dict[str, int | None]:
        return {h: self.known[h] for h in hashes if h in self.known}

    def enqueue(self, kind: str, payload: dict[str, object]) -> int:
        self.jobs.append((kind, payload))
        return len(self.jobs)

    def get_job(self, job_id: int) -> dict[str, object] | None:
        if not 0 < job_id <= len(self.jobs):
            return None
        kind, payload = self.jobs[job_id - 1]
        return {"kind": kind, "payload": payload, "status": "queued", "run_after": None}

    def get_source(self, source_id: int) -> Source | None:
        return None


@dataclass
class FakeInboxes:
    sources: dict[int, Source] = field(default_factory=dict)

    def ensure_inbox_source(self, user_id: int, root: str) -> Source:
        self.sources.setdefault(
            user_id, Source(100 + user_id, "Uploads", root, kind="inbox", owner_id=user_id)
        )
        return self.sources[user_id]


@dataclass
class World:
    use_case: UploadInbox
    library: FakeLibrary
    inboxes: FakeInboxes
    inbox_root: Path
    tmp: Path


@pytest.fixture
def world(tmp_path: Path) -> World:
    library, inboxes = FakeLibrary(), FakeInboxes()
    use_case = UploadInbox(
        inbox=inboxes,
        library=library,
        spool=DiskUploadSpool(tmp_path / "tmp"),
        clock=FakeClock(),
        inbox_root=tmp_path / "inbox",
        settings=UploadSettings(max_bytes=1000),
    )
    return World(use_case, library, inboxes, tmp_path / "inbox", tmp_path / "tmp")


def _spooled(world: World, content: bytes) -> SpooledUpload:
    writer = world.use_case.start()
    writer.write(content)
    return writer.finish()


def test_a_photo_lands_in_the_users_inbox_under_the_month(world: World) -> None:
    result = world.use_case.accept(ME, "IMG_1.JPG", _spooled(world, JPEG))
    assert result.outcome is UploadOutcome.STORED
    assert result.stored_as == "2026-09/IMG_1.JPG"
    assert (world.inbox_root / "7" / "2026-09" / "IMG_1.JPG").read_bytes() == JPEG
    assert list(world.tmp.iterdir()) == []


class MeasuredSpool(DiskUploadSpool):
    free = 0

    def free_bytes(self) -> int:
        return self.free


def test_a_file_is_refused_while_the_disk_is_under_its_free_space_floor(tmp_path: Path) -> None:
    gb = 1000**3
    spool = MeasuredSpool(tmp_path / "tmp")
    use_case = UploadInbox(
        inbox=FakeInboxes(),
        library=FakeLibrary(),
        spool=spool,
        clock=FakeClock(),
        inbox_root=tmp_path / "inbox",
        settings=UploadSettings(min_free_bytes=10 * gb),
    )
    spool.free = 10 * gb - 1
    refused = use_case.no_room("IMG_1.JPG")
    assert refused is not None and refused.outcome is UploadOutcome.REJECTED
    assert refused.name == "IMG_1.JPG" and refused.reason is not None
    assert "10.0 GB free" in refused.reason and "at least 10 GB" in refused.reason
    spool.free = 10 * gb
    assert use_case.no_room("IMG_1.JPG") is None, "exactly at the floor there is room"


def test_without_a_floor_every_file_has_room(world: World) -> None:
    assert world.use_case.no_room("IMG_1.JPG") is None


def test_finishing_a_batch_enqueues_one_import_of_the_inbox(world: World) -> None:
    results = [
        world.use_case.accept(ME, f"{n}.jpg", _spooled(world, JPEG + bytes([n]))) for n in (1, 2)
    ]
    job = world.use_case.finish_batch(7, results)
    assert job == 1
    assert world.library.jobs == [("scan_source", {"source_id": 107})]
    assert world.inboxes.sources[7].root == str(world.inbox_root / "7")


class OnceQueue:
    """enqueue_once as the repository does it: nothing while the same job is waiting."""

    def __init__(self) -> None:
        self.waiting: list[tuple[str, dict[str, object]]] = []

    def enqueue_once(self, kind: str, payload: dict[str, object] | None = None) -> int | None:
        if (kind, payload or {}) in self.waiting:
            return None
        self.waiting.append((kind, payload or {}))
        return len(self.waiting)


def test_a_file_stored_by_a_request_that_died_is_picked_up_by_the_rescan(world: World) -> None:
    """accept() moved it into the inbox; the server died before finish_batch queued the scan."""
    world.use_case.accept(ME, "first-ever.jpg", _spooled(world, JPEG))
    assert world.library.jobs == []
    queue = OnceQueue()
    sources = list(world.inboxes.sources.values())
    assert world.use_case.rescan(sources, queue.enqueue_once) == 1
    assert queue.waiting == [("scan_source", {"source_id": 107})]


def test_rescans_never_pile_up_and_only_touch_enabled_inboxes(world: World) -> None:
    queue = OnceQueue()
    sources = [
        Source(107, "Uploads (me)", str(world.inbox_root / "7"), kind="inbox", owner_id=7),
        Source(108, "Uploads (off)", "/x", enabled=False, kind="inbox", owner_id=8),
        Source(1, "Pictures", "/home/c/Pictures"),
        Source(2, "Phone", "/staging/2", kind="rclone", owner_id=7),
    ]
    world.inboxes.sources[7] = sources[0]
    world.use_case.accept(ME, "stranded.jpg", _spooled(world, JPEG))
    assert world.use_case.rescan(sources, queue.enqueue_once) == 1
    assert world.use_case.rescan(sources, queue.enqueue_once) == 0, "one is already waiting"
    assert queue.waiting == [("scan_source", {"source_id": 107})]


def _rescan(world: World) -> int:
    return world.use_case.rescan(list(world.inboxes.sources.values()), OnceQueue().enqueue_once)


def test_the_rescan_leaves_an_inbox_alone_once_an_import_has_looked_at_its_files(
    world: World,
) -> None:
    """It runs every hour; a scan each time meant about 24 "nothing new" import reports per
    inbox per day. Files stay in the inbox after import, so "not empty" is not the test."""
    world.use_case.accept(ME, "a.jpg", _spooled(world, JPEG))
    assert _rescan(world) == 1, "no import has run yet"
    world.library.runs[107] = ("done", datetime.now(UTC) + timedelta(seconds=5))
    assert _rescan(world) == 0, "the last import started after the newest file arrived"


def test_the_rescan_picks_up_a_file_that_arrived_after_the_last_import_started(
    world: World,
) -> None:
    world.library.runs[107] = ("done", datetime.now(UTC) - timedelta(hours=1))
    world.inboxes.ensure_inbox_source(7, str(world.inbox_root / "7"))
    assert _rescan(world) == 0, "an empty inbox has nothing waiting"
    world.use_case.accept(ME, "stranded.jpg", _spooled(world, JPEG))
    assert _rescan(world) == 1


@pytest.mark.parametrize("status", ["failed", "paused_low_disk"])
def test_the_rescan_tries_again_after_an_import_that_did_not_finish(
    world: World, status: str
) -> None:
    world.use_case.accept(ME, "a.jpg", _spooled(world, JPEG))
    world.library.runs[107] = (status, datetime.now(UTC) + timedelta(seconds=5))
    assert _rescan(world) == 1


def test_a_rescan_follows_a_moved_data_root(world: World) -> None:
    class MovingInboxes(FakeInboxes):
        def ensure_inbox_source(self, user_id: int, root: str) -> Source:
            self.sources[user_id] = Source(107, "Uploads", root, kind="inbox", owner_id=user_id)
            return self.sources[user_id]

    inboxes = MovingInboxes()
    use_case = UploadInbox(
        inbox=inboxes,
        library=world.library,
        spool=DiskUploadSpool(world.tmp),
        clock=FakeClock(),
        inbox_root=world.inbox_root,
    )
    stale = Source(107, "Uploads", "/old/place/inbox/7", kind="inbox", owner_id=7)
    use_case.rescan([stale], OnceQueue().enqueue_once)
    assert inboxes.sources[7].root == str(world.inbox_root / "7")


def test_nothing_stored_means_nothing_to_import(world: World) -> None:
    result = world.use_case.accept(ME, "x.jpg", _spooled(world, b"not a photo"))
    assert world.use_case.finish_batch(7, [result]) is None
    assert world.library.jobs == []


def test_non_photos_are_rejected_by_content_and_removed(world: World) -> None:
    result = world.use_case.accept(ME, "fake.jpg", _spooled(world, b"<html>hello</html>"))
    assert result.outcome is UploadOutcome.REJECTED
    assert result.reason is not None and "not a photo" in result.reason
    assert list(world.tmp.iterdir()) == []
    assert not world.inbox_root.exists()


def test_photos_already_in_the_library_are_not_stored_again(world: World) -> None:
    spooled = _spooled(world, JPEG)
    world.library.known[spooled.content_hash] = 55
    result = world.use_case.accept(ME, "IMG_1.JPG", spooled)
    assert (result.outcome, result.asset_id) == (UploadOutcome.DUPLICATE, 55)
    assert list(world.tmp.iterdir()) == []


def test_too_large_is_reported_as_a_rejection(world: World) -> None:
    result = world.use_case.too_large("big.jpg")
    assert result.outcome is UploadOutcome.REJECTED
    assert "0.001 MB" in (result.reason or "")


def test_missing_lists_only_hashes_not_in_the_library(world: World) -> None:
    known, unknown = "a" * 64, "b" * 64
    world.library.known[known] = 1
    assert world.use_case.missing(ME, [known, unknown, unknown]) == [unknown]


def test_missing_refuses_malformed_or_too_many_hashes(world: World) -> None:
    with pytest.raises(ValueError, match="not a content hash"):
        world.use_case.missing(ME, ["xyz"])
    with pytest.raises(ValueError, match="at most"):
        world.use_case.missing(ME, ["a" * 64] * 5001)


# --- device tokens ---------------------------------------------------------------------------


@dataclass
class FakeDevices:
    rows: list[tuple[Device, str]] = field(default_factory=list)

    def add_device(
        self, user_id: int, name: str, platform: str, token_hash: str, now: datetime
    ) -> Device:
        device = Device(len(self.rows) + 1, user_id, name, platform, now)
        self.rows.append((device, token_hash))
        return device

    def list_devices(self, user_id: int) -> list[Device]:
        return [d for d, _ in self.rows if d.user_id == user_id]

    def revoke_device(self, user_id: int, device_id: int, now: datetime) -> bool:
        self.rows = [
            (d, h) for d, h in self.rows if not (d.id == device_id and d.user_id == user_id)
        ]
        return True

    def user_for_token_hash(self, token_hash: str, now: datetime) -> int | None:
        return next((d.user_id for d, h in self.rows if h == token_hash), None)


def test_a_token_is_shown_once_and_only_its_hash_is_stored() -> None:
    store = FakeDevices()
    tokens = DeviceTokens(store, FakeClock())
    device, token = tokens.create(3, "C's iPhone", "ios")
    assert token.startswith("pa_dev_") and len(token) > 40
    assert store.rows[0][1] == hash_token(token) != token
    assert tokens.authenticate(token) == 3
    assert tokens.authenticate("pa_dev_wrong") is None
    assert tokens.authenticate("not-ours") is None
    assert tokens.list(3) == [device]
    assert tokens.revoke(3, device.id)
    assert tokens.authenticate(token) is None


@pytest.mark.parametrize(("name", "platform"), [("", "ios"), ("x" * 61, "ios"), ("ok", "nokia")])
def test_device_names_and_platforms_are_checked(name: str, platform: str) -> None:
    with pytest.raises(ValueError):
        DeviceTokens(FakeDevices(), FakeClock()).create(1, name, platform)


def test_device_names_lose_control_characters() -> None:
    device, _ = DeviceTokens(FakeDevices(), FakeClock()).create(1, " iPhone\n ", "ios")
    assert device.name == "iPhone"
