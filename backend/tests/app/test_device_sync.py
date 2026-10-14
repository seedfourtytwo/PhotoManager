"""Keep on my phone (FEATURES 10.6): one device's list, its manifest, and what it may fetch.

The library is real (SQLite in memory, the real visibility rule); what each rule names is a
small fake, so these tests are about merging, access and paging, not about albums or people.
"""

from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from photo_assistant.adapters.sqlite_device_sync import SqliteDeviceSync
from photo_assistant.adapters.sqlite_integrations import SqliteDevices
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.app.device_sync import (
    DeviceNotFoundError,
    DeviceSync,
    SyncPhotoNotFoundError,
    SyncRuleNotFoundError,
    SyncTargetNotFoundError,
)
from photo_assistant.domain.access import Level, Role, SourceAccess, Viewer
from photo_assistant.domain.device_sync import (
    MAX_RULES,
    InvalidSyncRuleError,
    SyncKind,
    SyncMode,
    SyncTarget,
)
from photo_assistant.ports.device_sync import Resolved
from photo_assistant.ports.upload import Device
from tests.factories import NOW, new_asset
from tests.fakes import FakeClock

SUMMER = SyncTarget(SyncKind.ALBUM, ref_id=1)
LEA = SyncTarget(SyncKind.PERSON, ref_id=1)
SCREENSHOTS = SyncTarget(SyncKind.FILTER, filters='{"q":"tag:screenshot"}')
GONE = SyncTarget(SyncKind.ALBUM, ref_id=99)


@dataclass
class FakeScopes:
    """Each target names fixed photos, the same for every viewer (visibility comes after)."""

    names: dict[SyncTarget, Resolved] = field(default_factory=dict)

    def resolve(self, viewer: Viewer, target: SyncTarget) -> Resolved | None:
        return self.names.get(target)


@dataclass
class World:
    sync: DeviceSync
    repo: SqliteRepository
    scopes: FakeScopes
    clock: FakeClock
    devices: SqliteDevices
    lea: Viewer
    phone: Device
    photos: dict[str, int]


@pytest.fixture
def world() -> World:
    """Lea (a member), her phone, an album and a person to name. Her source lets her
    download p1-p4 and only view p5; she hid p3; p4 is in the trash; p6 is in a source she
    cannot see at all."""
    db = Database.open(":memory:")
    repo = SqliteRepository(db)
    admin = repo.add_user("c", "C", "hash", Role.ADMIN)
    lea = repo.add_user("lea", "Lea", "hash", Role.MEMBER)
    family = repo.add_source(
        "family", "/f", admin.id, access=SourceAccess(None, ((lea.id, Level.DOWNLOAD),))
    )
    viewing = repo.add_source(
        "view", "/v", admin.id, access=SourceAccess(None, ((lea.id, Level.VIEW),))
    )
    secret = repo.add_source("secret", "/s", admin.id, access=SourceAccess(None, ()))
    photos: dict[str, int] = {}
    placed = [("p1", family), ("p2", family), ("p3", family), ("p4", family)]
    for n, (name, source) in enumerate([*placed, ("p5", viewing), ("p6", secret)], start=1):
        photos[name] = repo.add_asset(new_asset(n, byte_size=1000 * n), NOW)
        repo.add_asset_source(photos[name], source.id, f"{name}.jpg")
    repo.set_user_state(lea.id, [photos["p3"]], hidden=True)
    repo.trash_assets([photos["p4"]], admin.id, NOW)
    assert repo.create_album(lea.id, "Summer", "", NOW) == SUMMER.ref_id  # rules name real rows
    db.writer.execute("INSERT INTO person (id, name) VALUES (?, 'Lea')", (LEA.ref_id,))
    clock = FakeClock()
    devices = SqliteDevices(db)
    phone = devices.add_device(lea.id, "Lea's iPhone", "ios", "h", NOW)
    scopes = FakeScopes()
    sync = DeviceSync(devices, SqliteDeviceSync(db), scopes, repo, clock)
    return World(sync, repo, scopes, clock, devices, Viewer.of(lea), phone, photos)


def _names(world: World, *ids_of: str) -> Resolved:
    return Resolved(None, [world.photos[n] for n in ids_of])


def _ids(world: World, *names: str) -> list[int]:
    return sorted(world.photos[n] for n in names)


def test_the_list_is_the_includes_minus_the_excludes(world: World) -> None:
    world.scopes.names = {
        SUMMER: _names(world, "p1", "p2"),
        LEA: _names(world, "p2"),
        SCREENSHOTS: _names(world, "p1"),
    }
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    world.sync.keep(world.lea, world.phone.id, LEA, SyncMode.INCLUDE)
    world.sync.keep(world.lea, world.phone.id, SCREENSHOTS, SyncMode.EXCLUDE)

    page = world.sync.manifest(world.lea, world.phone, new_only=False, after=None, limit=50)
    assert [v.id for v in page.items] == _ids(world, "p2")
    assert (page.total, page.next_after) == (1, None)


def test_only_photos_she_may_download_and_has_not_hidden_or_trashed(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1", "p2", "p3", "p4", "p5", "p6")}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)

    page = world.sync.manifest(world.lea, world.phone, new_only=False, after=None, limit=50)

    assert [v.id for v in page.items] == _ids(world, "p1", "p2")
    assert page.total_bytes == 1000 + 2000


def test_new_only_leaves_out_what_the_phone_said_it_saved(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1", "p2")}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    world.sync.original(world.lea, world.phone, world.photos["p1"])
    fetched = world.sync.manifest(world.lea, world.phone, new_only=True, after=None, limit=50)
    assert len(fetched.items) == 2, "fetching alone marks nothing: the phone may not have saved it"
    assert world.sync.saved(world.lea, world.phone, [world.photos["p1"]]) == 1

    page = world.sync.manifest(world.lea, world.phone, new_only=True, after=None, limit=50)
    assert [v.id for v in page.items] == _ids(world, "p2")
    assert page.total == 2, "the whole list is still two photos"

    assert world.sync.resend(world.lea, world.phone.id) == 1
    again = world.sync.manifest(world.lea, world.phone, new_only=True, after=None, limit=50)
    assert [v.id for v in again.items] == _ids(world, "p1", "p2")


def test_only_photos_on_the_list_can_be_said_saved(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1")}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    with pytest.raises(InvalidSyncRuleError, match="not on this device's list"):
        world.sync.saved(world.lea, world.phone, [world.photos["p1"], world.photos["p2"]])
    page = world.sync.manifest(world.lea, world.phone, new_only=True, after=None, limit=50)
    assert [v.id for v in page.items] == _ids(world, "p1"), "nothing was marked"


def test_pages_follow_one_another(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1", "p2")}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    first = world.sync.manifest(world.lea, world.phone, new_only=False, after=None, limit=1)
    assert first.next_after == world.photos["p1"]
    second = world.sync.manifest(
        world.lea, world.phone, new_only=False, after=first.next_after, limit=1
    )
    assert [v.id for v in second.items] == _ids(world, "p2") and second.next_after is None


def test_asking_for_the_list_is_recorded(world: World) -> None:
    world.clock.advance(timedelta(hours=2))
    world.sync.manifest(world.lea, world.phone, new_only=True, after=None, limit=50)
    summary = world.sync.summary(world.lea, world.phone.id)
    assert summary.device.last_sync_at == NOW + timedelta(hours=2)


def test_a_photo_off_the_list_cannot_be_fetched_even_if_she_may_see_it(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1")}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    for name in ("p2", "p3", "p5", "p6"):
        with pytest.raises(SyncPhotoNotFoundError):
            world.sync.original(world.lea, world.phone, world.photos[name])


def test_the_summary_counts_each_rule_and_the_whole_list(world: World) -> None:
    world.scopes.names = {
        SUMMER: Resolved("Summer", [world.photos["p1"], world.photos["p2"]]),
        SCREENSHOTS: _names(world, "p2", "p6"),
    }
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    world.sync.keep(world.lea, world.phone.id, SCREENSHOTS, SyncMode.EXCLUDE)

    summary = world.sync.summary(world.lea, world.phone.id)

    assert [(r.label, r.count, r.rule.mode) for r in summary.rules] == [
        ("Summer", 2, SyncMode.INCLUDE),
        (None, 2, SyncMode.EXCLUDE),
    ]
    assert (summary.count, summary.bytes, summary.sent) == (1, 1000, 0)


def test_a_rule_says_how_many_of_its_photos_she_may_only_view(world: World) -> None:
    """p5 comes from a source that lets Lea view, not download: it can't go to her phone,
    and the summary says so rather than leave her wondering."""
    world.scopes.names = {SUMMER: Resolved("Summer", _ids(world, "p1", "p3", "p5"))}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    (rule,) = world.sync.summary(world.lea, world.phone.id).rules
    assert (rule.count, rule.view_only) == (3, 1), "p3 is hidden, not view-only"


def test_a_rule_whose_album_she_can_no_longer_see_names_nothing(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1")}
    world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    world.scopes.names = {}  # unshared since
    summary = world.sync.summary(world.lea, world.phone.id)
    assert [(r.label, r.count, r.gone) for r in summary.rules] == [(None, 0, True)]
    assert summary.count == 0


def test_she_cannot_keep_what_she_cannot_see(world: World) -> None:
    with pytest.raises(SyncTargetNotFoundError):
        world.sync.keep(world.lea, world.phone.id, GONE, SyncMode.INCLUDE)


def test_a_badly_formed_target_is_refused(world: World) -> None:
    with pytest.raises(InvalidSyncRuleError):
        world.sync.keep(world.lea, world.phone.id, SyncTarget(SyncKind.ALBUM), SyncMode.INCLUDE)


def test_a_device_holds_a_bounded_number_of_rules(world: World) -> None:
    targets = [SyncTarget(SyncKind.FILTER, filters=f'{{"year":{2000 + n}}}') for n in range(51)]
    world.scopes.names = {t: Resolved(None, []) for t in targets}
    for target in targets[:MAX_RULES]:
        world.sync.keep(world.lea, world.phone.id, target, SyncMode.INCLUDE)
    world.sync.keep(world.lea, world.phone.id, targets[0], SyncMode.EXCLUDE)  # a change is fine
    with pytest.raises(InvalidSyncRuleError, match=str(MAX_RULES)):
        world.sync.keep(world.lea, world.phone.id, targets[MAX_RULES], SyncMode.INCLUDE)


def test_rules_are_dropped_by_id_on_her_own_device(world: World) -> None:
    world.scopes.names = {SUMMER: _names(world, "p1")}
    rule = world.sync.keep(world.lea, world.phone.id, SUMMER, SyncMode.INCLUDE)
    with pytest.raises(SyncRuleNotFoundError):
        world.sync.drop(world.lea, world.phone.id, rule.id + 1)
    world.sync.drop(world.lea, world.phone.id, rule.id)
    assert world.sync.summary(world.lea, world.phone.id).rules == []


def test_someone_elses_or_a_revoked_device_is_not_found(world: World) -> None:
    admin = Viewer(1, Role.ADMIN)
    with pytest.raises(DeviceNotFoundError):
        world.sync.summary(admin, world.phone.id)
    world.devices.revoke_device(world.lea.user_id, world.phone.id, NOW)
    with pytest.raises(DeviceNotFoundError):
        world.sync.summary(world.lea, world.phone.id)
