"""UploadInbox and DeviceTokens with a real temp-folder spool and in-memory fakes."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.upload_spool import DiskUploadSpool
from photo_assistant.app.devices import DeviceTokens, hash_token
from photo_assistant.app.upload import UploadInbox, UploadOutcome, UploadSettings
from photo_assistant.domain.model import Source
from photo_assistant.ports.upload import Device, SpooledUpload
from tests.factories import NOW

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"pixels" * 10


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class FakeLibrary:
    known: dict[str, int] = field(default_factory=dict)
    jobs: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def find_asset_id_by_hash(self, content_hash: str) -> int | None:
        return self.known.get(content_hash)

    def enqueue(self, kind: str, payload: dict[str, object]) -> int:
        self.jobs.append((kind, payload))
        return len(self.jobs)


@dataclass
class FakeInboxes:
    sources: dict[int, Source] = field(default_factory=dict)

    def ensure_inbox_source(self, user_id: int, root: str) -> Source:
        self.sources.setdefault(user_id, Source(100 + user_id, "Uploads", root, kind="inbox"))
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
        clock=FixedClock(),
        inbox_root=tmp_path / "inbox",
        settings=UploadSettings(max_bytes=1000),
    )
    return World(use_case, library, inboxes, tmp_path / "inbox", tmp_path / "tmp")


def _spooled(world: World, content: bytes) -> SpooledUpload:
    writer = world.use_case.start()
    writer.write(content)
    return writer.finish()


def test_a_photo_lands_in_the_users_inbox_under_the_month(world: World) -> None:
    result = world.use_case.accept(7, "IMG_1.JPG", _spooled(world, JPEG))
    assert result.outcome is UploadOutcome.STORED
    assert result.stored_as == "2026-09/IMG_1.JPG"
    assert (world.inbox_root / "7" / "2026-09" / "IMG_1.JPG").read_bytes() == JPEG
    assert list(world.tmp.iterdir()) == []


def test_finishing_a_batch_enqueues_one_import_of_the_inbox(world: World) -> None:
    results = [
        world.use_case.accept(7, f"{n}.jpg", _spooled(world, JPEG + bytes([n]))) for n in (1, 2)
    ]
    job = world.use_case.finish_batch(7, results)
    assert job == 1
    assert world.library.jobs == [("scan_source", {"source_id": 107})]
    assert world.inboxes.sources[7].root == str(world.inbox_root / "7")


def test_nothing_stored_means_nothing_to_import(world: World) -> None:
    result = world.use_case.accept(7, "x.jpg", _spooled(world, b"not a photo"))
    assert world.use_case.finish_batch(7, [result]) is None
    assert world.library.jobs == []


def test_non_photos_are_rejected_by_content_and_removed(world: World) -> None:
    result = world.use_case.accept(7, "fake.jpg", _spooled(world, b"<html>hello</html>"))
    assert result.outcome is UploadOutcome.REJECTED
    assert result.reason is not None and "not a photo" in result.reason
    assert list(world.tmp.iterdir()) == []
    assert not world.inbox_root.exists()


def test_photos_already_in_the_library_are_not_stored_again(world: World) -> None:
    spooled = _spooled(world, JPEG)
    world.library.known[spooled.content_hash] = 55
    result = world.use_case.accept(7, "IMG_1.JPG", spooled)
    assert (result.outcome, result.asset_id) == (UploadOutcome.DUPLICATE, 55)
    assert list(world.tmp.iterdir()) == []


def test_too_large_is_reported_as_a_rejection(world: World) -> None:
    result = world.use_case.too_large("big.jpg")
    assert result.outcome is UploadOutcome.REJECTED
    assert "0.001 MB" in (result.reason or "")


def test_missing_lists_only_hashes_not_in_the_library(world: World) -> None:
    known, unknown = "a" * 64, "b" * 64
    world.library.known[known] = 1
    assert world.use_case.missing([known, unknown, unknown]) == [unknown]


def test_missing_refuses_malformed_or_too_many_hashes(world: World) -> None:
    with pytest.raises(ValueError, match="not a content hash"):
        world.use_case.missing(["xyz"])
    with pytest.raises(ValueError, match="at most"):
        world.use_case.missing(["a" * 64] * 5001)


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
    tokens = DeviceTokens(store, FixedClock())
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
        DeviceTokens(FakeDevices(), FixedClock()).create(1, name, platform)


def test_device_names_lose_control_characters() -> None:
    device, _ = DeviceTokens(FakeDevices(), FixedClock()).create(1, " iPhone\n ", "ios")
    assert device.name == "iPhone"
