import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_integrations import (
    SqliteAILog,
    SqliteDevices,
    SqliteInboxes,
    SqliteRemoteSources,
)
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.domain.remote_source import RemoteConfig, RemoteConfigError
from photo_assistant.ports.ai import AICall

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = open_database(":memory:")
    yield connection
    connection.close()


def test_ai_calls_are_logged_as_json_summaries(conn: sqlite3.Connection) -> None:
    log = SqliteAILog(conn)
    log.record(
        AICall("caption", "m", {"images": [{"bytes": 10}]}, {"status": 200}, True, 12, None, 1)
    )
    log.record(AICall("plan_album", "p", {}, {}, False, 5, "bad json", 2))
    rows = log.recent(10)
    assert [r["capability"] for r in rows] == ["plan_album", "caption"]
    assert rows[1]["request"] == {"images": [{"bytes": 10}]}
    assert (rows[0]["ok"], rows[0]["error"], rows[0]["attempt"]) == (False, "bad json", 2)


def test_remote_sources_live_in_staging_and_keep_only_the_remote_name(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    store = SqliteRemoteSources(conn)
    source_id = store.add_remote_source("MEGA", RemoteConfig("mega", "Photos"), tmp_path)
    source = SqliteRepository(conn).get_source(source_id)
    assert source is not None
    assert (source.kind, source.label, source.root) == ("rclone", "MEGA", str(tmp_path / "1"))
    assert store.remote_config(source_id) == RemoteConfig("mega", "Photos")
    row = conn.execute("SELECT config_json FROM source WHERE id = ?", (source_id,)).fetchone()
    assert json.loads(row[0]) == {"remote": "mega", "path": "Photos"}


def test_remote_config_is_none_for_other_sources(conn: sqlite3.Connection) -> None:
    folder = SqliteRepository(conn).add_source("Pictures", "/pictures")
    store = SqliteRemoteSources(conn)
    assert store.remote_config(folder.id) is None
    assert store.remote_config(404) is None


def test_a_tampered_remote_config_is_refused(conn: sqlite3.Connection, tmp_path: Path) -> None:
    store = SqliteRemoteSources(conn)
    source_id = store.add_remote_source("x", RemoteConfig("mega"), tmp_path)
    conn.execute("UPDATE source SET config_json = ? WHERE id = ?", ('{"remote": "-x"}', source_id))
    with pytest.raises(RemoteConfigError):
        store.remote_config(source_id)
    conn.execute("UPDATE source SET config_json = '[1]' WHERE id = ?", (source_id,))
    with pytest.raises(RemoteConfigError):
        store.remote_config(source_id)


def test_set_root_moves_a_source(conn: sqlite3.Connection, tmp_path: Path) -> None:
    store = SqliteRemoteSources(conn)
    source_id = store.add_remote_source("x", RemoteConfig("mega"), tmp_path)
    store.set_root(source_id, "/new/staging/1")
    source = SqliteRepository(conn).get_source(source_id)
    assert source is not None and source.root == "/new/staging/1"


def test_each_user_has_one_inbox_source(conn: sqlite3.Connection) -> None:
    inboxes = SqliteInboxes(conn)
    first = inboxes.ensure_inbox_source(7, "/data/inbox/7")
    again = inboxes.ensure_inbox_source(7, "/data/inbox/7")
    other = inboxes.ensure_inbox_source(8, "/data/inbox/8")
    assert first == again
    assert (first.kind, first.root) == ("inbox", "/data/inbox/7")
    assert other.id != first.id


def test_an_inbox_follows_a_moved_data_root(conn: sqlite3.Connection) -> None:
    inboxes = SqliteInboxes(conn)
    first = inboxes.ensure_inbox_source(7, "/old/inbox/7")
    moved = inboxes.ensure_inbox_source(7, "/new/inbox/7")
    assert (moved.id, moved.root) == (first.id, "/new/inbox/7")


def test_devices_are_listed_per_user_and_found_by_token_hash(conn: sqlite3.Connection) -> None:
    devices = SqliteDevices(conn)
    phone = devices.add_device(1, "C's iPhone", "ios", "h1", NOW)
    devices.add_device(2, "Tablet", "android", "h2", NOW)
    assert [d.name for d in devices.list_devices(1)] == ["C's iPhone"]
    assert phone.created_at == NOW and phone.last_used_at is None
    later = NOW + timedelta(hours=1)
    assert devices.user_for_token_hash("h1", later) == 1
    assert devices.list_devices(1)[0].last_used_at == later
    assert devices.user_for_token_hash("nope", later) is None


def test_revoked_devices_no_longer_authenticate(conn: sqlite3.Connection) -> None:
    devices = SqliteDevices(conn)
    phone = devices.add_device(1, "iPhone", "ios", "h1", NOW)
    assert not devices.revoke_device(2, phone.id, NOW)  # not yours
    assert devices.revoke_device(1, phone.id, NOW)
    assert not devices.revoke_device(1, phone.id, NOW)  # already revoked
    assert devices.user_for_token_hash("h1", NOW) is None
    assert devices.list_devices(1)[0].revoked_at == NOW
