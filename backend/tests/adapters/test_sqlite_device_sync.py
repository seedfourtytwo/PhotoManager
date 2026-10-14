"""SQLite storage of "Keep on my phone": rules per device, and what each device got."""

from datetime import UTC, datetime, timedelta

import pytest

from photo_assistant.adapters.sqlite_device_sync import SqliteDeviceSync
from photo_assistant.adapters.sqlite_integrations import SqliteDevices
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.domain.device_sync import SyncKind, SyncMode, SyncTarget
from tests.factories import new_asset

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
SCREENSHOTS = SyncTarget(SyncKind.FILTER, filters='{"q":"tag:screenshot"}')


@pytest.fixture
def store(db: Database) -> SqliteDeviceSync:
    db.writer.execute(
        "INSERT INTO user (id, username, display_name, password_hash, role) "
        "VALUES (1, 'c', 'C', 'x', 'member')"
    )
    devices = SqliteDevices(db)
    devices.add_device(1, "iPhone", "ios", "h1", NOW)
    devices.add_device(1, "iPad", "ios", "h2", NOW)
    return SqliteDeviceSync(db)


def _album(db: Database) -> int:
    return SqliteRepository(db).create_album(1, "Summer", "", NOW)


def test_rules_are_kept_per_device_and_a_thing_is_named_once(
    store: SqliteDeviceSync, db: Database
) -> None:
    album = SyncTarget(SyncKind.ALBUM, ref_id=_album(db))
    kept = store.put_sync_rule(1, album, SyncMode.INCLUDE, NOW)
    store.put_sync_rule(1, SCREENSHOTS, SyncMode.EXCLUDE, NOW)
    again = store.put_sync_rule(1, album, SyncMode.EXCLUDE, NOW)

    assert again.id == kept.id and again.mode is SyncMode.EXCLUDE
    assert [(r.target, r.mode) for r in store.sync_rules(1)] == [
        (album, SyncMode.EXCLUDE),
        (SCREENSHOTS, SyncMode.EXCLUDE),
    ]
    assert store.sync_rules(2) == []


def test_a_rule_is_deleted_only_through_its_own_device(store: SqliteDeviceSync) -> None:
    rule = store.put_sync_rule(1, SCREENSHOTS, SyncMode.EXCLUDE, NOW)
    assert not store.delete_sync_rule(2, rule.id)
    assert store.delete_sync_rule(1, rule.id)
    assert not store.delete_sync_rule(1, rule.id)
    assert store.sync_rules(1) == []


def test_a_deleted_album_takes_its_rule_with_it(store: SqliteDeviceSync, db: Database) -> None:
    album_id = _album(db)
    store.put_sync_rule(1, SyncTarget(SyncKind.ALBUM, ref_id=album_id), SyncMode.INCLUDE, NOW)
    SqliteRepository(db).delete_album(album_id)
    assert store.sync_rules(1) == []


def test_sent_photos_are_remembered_per_device_until_forgotten(
    store: SqliteDeviceSync, db: Database
) -> None:
    repo = SqliteRepository(db)
    a, b = (repo.add_asset(new_asset(n), NOW) for n in (1, 2))
    store.mark_sent(1, [a], NOW)
    store.mark_sent(1, [a, b], NOW + timedelta(minutes=1))  # a saved twice: harmless
    assert store.sent_ids(1) == {a, b}
    assert store.sent_ids(2) == set()
    assert store.forget_sent(1) == 2
    assert store.sent_ids(1) == set()


def test_asking_for_the_list_is_recorded_on_the_device(
    store: SqliteDeviceSync, db: Database
) -> None:
    store.record_sync(1, NOW)
    (phone, _) = SqliteDevices(db).list_devices(1)
    assert phone.last_sync_at == NOW
