"""The merged migration chain (core 0004-0012, ai-sources 0013-0014, ml 0015, ops 0016).

A fresh library must reach the latest version, and a real M1-era library (version 3, with
photos in it) must upgrade in place without losing anything, after a snapshot.
"""

import sqlite3
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, _migrations, open_database
from photo_assistant.domain.access import Level

EXPECTED_TABLES = {
    # M1
    "source", "asset", "asset_source", "import_run", "import_item", "job",
    # core (M2)
    "user", "session", "login_failure", "source_access", "album", "purged_hash",
    # ai-sources
    "ai_log", "inbox", "device",
    # ml
    "ml_task", "clip_embedding", "face", "person", "tag", "asset_tag", "asset_ml_flag",
    # ops
    "backup_target", "backup_run",
}  # fmt: skip


def _latest() -> int:
    return max(n for n, _ in _migrations())


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def _make_v3_library(db: Path) -> None:
    """A library as M1 left it: migrations 1-3 and two photos from one folder."""
    conn = sqlite3.connect(db)
    for number, sql in _migrations():
        if number <= 3:
            conn.executescript(f"BEGIN;{sql};PRAGMA user_version = {number};COMMIT;")
    conn.execute("INSERT INTO source (id, label, root) VALUES (1, 'Pictures', '/home/c/Pictures')")
    for i in (1, 2):
        conn.execute(
            """INSERT INTO asset (id, content_hash, kind, mime_type, byte_size, width, height,
                   taken_at, date_source, library_path, thumb_path, imported_at)
               VALUES (?, ?, 'photo', 'image/jpeg', 1000, 800, 600, ?, 'exif', ?, ?,
                       '2026-08-01T10:00:00')""",
            (
                i,
                f"{i:064x}",
                f"2019-07-0{i}T18:30:00",
                f"originals/2019/07/{i:064x}.jpg",
                f"derived/thumb/00/{i:064x}.webp",
            ),
        )
        conn.execute(
            """INSERT INTO asset_source (asset_id, source_id, relative_path, byte_size,
                   mtime_ns, ctime_ns) VALUES (?, 1, ?, 1000, 1, 1)""",
            (i, f"IMG_{i}.JPG"),
        )
    conn.execute(
        """INSERT INTO import_run (source_id, status, started_at, finished_at, summary_json)
           VALUES (1, 'done', '2026-08-01T10:00:00', '2026-08-01T10:01:00', '{}')"""
    )
    conn.execute("INSERT INTO job (kind, payload_json) VALUES ('preview', '{\"asset_id\": 1}')")
    conn.commit()
    conn.close()


def test_migrations_are_numbered_one_by_one_without_gaps() -> None:
    numbers = [n for n, _ in _migrations()]
    assert numbers == list(range(1, len(numbers) + 1))
    assert _latest() == 20


def test_a_fresh_library_reaches_the_latest_version(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "library.db", backup_dir=tmp_path / "backups")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _latest()
    assert _tables(conn) >= EXPECTED_TABLES
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not (tmp_path / "backups").exists()


def test_a_v3_library_with_photos_upgrades_cleanly_after_a_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    _make_v3_library(db)

    conn = open_database(db, backup_dir=tmp_path / "backups")

    assert conn.execute("PRAGMA user_version").fetchone()[0] == _latest()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert _tables(conn) >= EXPECTED_TABLES
    # the snapshot is the untouched v3 library
    (snapshot,) = (tmp_path / "backups").glob("library-v3-*.db")
    old = sqlite3.connect(snapshot)
    assert old.execute("PRAGMA user_version").fetchone()[0] == 3
    assert old.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 2
    # the photos, their origins and history are all still there
    repo = SqliteRepository(conn)
    assert [s.label for s in repo.list_sources()] == ["Pictures"]
    assert repo.count_assets() == 2
    assert repo.asset_id_for_source_path(1, "IMG_2.JPG") == 2
    assert len(repo.list_jobs()) == 1
    # M1 sources stay open to everyone at the contract default; owners are set by the M2 setup
    assert repo.get_access(1) == (Level.DOWNLOAD, [])
    first_sources = conn.execute("SELECT first_source_id FROM asset ORDER BY id").fetchall()
    assert [r[0] for r in first_sources] == [1, 1]
    # nothing new is attached to the old rows by accident
    assert conn.execute("SELECT config_json FROM source").fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM inbox").fetchone()[0] == 0


def test_an_upgraded_library_reopens_without_a_second_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    _make_v3_library(db)
    open_database(db, backup_dir=tmp_path / "backups").close()
    open_database(db, backup_dir=tmp_path / "backups").close()
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def _old_snapshots(folder: Path) -> list[str]:
    """Seven pre-migration copies from earlier upgrades (oldest first), and a file of the
    user's own in the same folder."""
    folder.mkdir()
    names = [f"library-v{v}-202501{v:02d}T120000000000.db" for v in range(8, 15)]
    for name in names:
        (folder / name).write_bytes(b"old copy")
    (folder / "my-own-copy.db").write_bytes(b"not ours")
    (folder / "library-v9-notes.txt").write_text("not a snapshot")
    return names


def test_only_the_newest_five_pre_migration_copies_are_kept(tmp_path: Path) -> None:
    """Nothing ever deleted them: one copy of the whole database per upgrade, for ever."""
    backups = tmp_path / "backups"
    old = _old_snapshots(backups)
    db = tmp_path / "library.db"
    _make_v3_library(db)

    open_database(db, backup_dir=backups).close()

    (new,) = [p.name for p in backups.glob("library-v3-*.db")] or [""]
    kept = sorted(p.name for p in backups.iterdir())
    assert kept == sorted([*old[3:], new, "my-own-copy.db", "library-v9-notes.txt"])
    # newest by when it was made: as text, v10 to v14 sort before v8 and v9
    assert "library-v9-20250109T120000000000.db" not in kept


def test_no_copy_is_deleted_when_the_migration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from photo_assistant.adapters import sqlite_database

    backups = tmp_path / "backups"
    old = _old_snapshots(backups)
    db = tmp_path / "library.db"
    _make_v3_library(db)
    broken = [*_migrations(), (_latest() + 1, "INSERT INTO no_such_table VALUES (1);")]
    monkeypatch.setattr(sqlite_database, "migrations", lambda: broken)

    with pytest.raises(sqlite3.OperationalError):
        open_database(db, backup_dir=backups)

    assert {p.name for p in backups.glob("library-v*.db")} >= set(old), "all still there"
    assert len(list(backups.glob("library-v3-*.db"))) == 1, "and the copy made just before"


def _make_v16_library(db: Path) -> None:
    """A library as M2 left it (version 16): accounts, an inbox, devices, a backup target with
    runs, a private photo, a degenerate crop and an mtime date with microseconds."""
    conn = sqlite3.connect(db)
    for number, sql in _migrations():
        if number <= 16:
            conn.executescript(f"BEGIN;{sql};PRAGMA user_version = {number};COMMIT;")
    conn.executescript(
        """
        INSERT INTO user (id, username, display_name, password_hash, role)
            VALUES (1, 'c', 'C', 'x', 'admin'), (2, 'lea', 'Lea', 'x', 'member');
        INSERT INTO source (id, label, root, owner_id) VALUES (1, 'Pictures', '/p', 1);
        INSERT INTO source (id, kind, label, root, owner_id) VALUES (2, 'inbox', 'Up', '/i/2', 2);
        INSERT INTO inbox (user_id, source_id) VALUES (2, 2);
        INSERT INTO device (user_id, name, token_hash, created_at)
            VALUES (2, 'phone', 'h1', '2026-09-01T00:00:00'), (2, 'pad', 'h2', '2026-09-01');
        INSERT INTO asset (id, content_hash, kind, mime_type, byte_size, width, height, taken_at,
                date_source, library_path, imported_at, first_source_id, private)
            VALUES (1, 'a', 'photo', 'image/jpeg', 1, 4, 3, '2020-01-01T10:00:00.729120',
                    'file_mtime', 'originals/a.jpg', '2026-09-01', 2, 1),
                   (2, 'b', 'photo', 'image/jpeg', 1, 4, 3, '2020-01-01T11:00:00',
                    'exif', 'originals/b.jpg', '2026-09-01', 1, 0);
        INSERT INTO asset_source (asset_id, source_id, relative_path) VALUES (1, 2, 'a.jpg'),
            (2, 1, 'b.jpg');
        INSERT INTO edit_recipe (asset_id, recipe_json, updated_by, updated_at)
            VALUES (2, '{"rotate": 0, "crop": {"x": 0, "y": 0, "w": 1e-12, "h": 0.5}}', 1, 'x');
        INSERT INTO backup_target (id, label, kind, repository, password_file, retention_json,
                created_at) VALUES (1, 'Disk', 'local', '/b', '/pw', '{}', '2026-09-01');
        INSERT INTO backup_run (target_id, status, started_at) VALUES (1, 'succeeded', 'x'),
            (1, 'failed', 'y');
        """
    )
    conn.close()


def test_a_v16_library_upgrades_with_foreign_keys_and_its_data(tmp_path: Path) -> None:
    """0017 (fix/backend): FKs on inbox/device/backup_run, private_by, cleaned recipes."""
    db = tmp_path / "library.db"
    _make_v16_library(db)
    conn = open_database(db, backup_dir=tmp_path / "backups")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _latest()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert [tuple(r) for r in conn.execute("SELECT user_id, source_id FROM inbox")] == [(2, 2)]
    assert conn.execute("SELECT COUNT(*) FROM device").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM backup_run").fetchone()[0] == 2
    # private photos keep their meaning: private to the owner of their first source (lea)
    assert conn.execute("SELECT private_by FROM asset WHERE id = 1").fetchone()[0] == 2
    assert conn.execute("SELECT taken_at FROM asset WHERE id = 1").fetchone()[0] == (
        "2020-01-01T10:00:00"
    )
    assert conn.execute("SELECT COUNT(*) FROM edit_recipe").fetchone()[0] == 0
    assert conn.execute("SELECT edit_version FROM asset WHERE id = 2").fetchone()[0] == 1
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"device_by_user", "backup_run_by_target", "asset_live_timeline"} <= indexes
    # the new foreign keys cascade
    conn.execute("DELETE FROM backup_target WHERE id = 1")
    assert conn.execute("SELECT COUNT(*) FROM backup_run").fetchone()[0] == 0
    for table in ("inbox", "device"):
        keys = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        assert ("user", "user_id", "CASCADE") in {
            (k["table"], k["from"], k["on_delete"]) for k in keys
        }
    conn.execute(
        "INSERT INTO user (id, username, display_name, password_hash, role) "
        "VALUES (3, 'gone', 'Gone', 'x', 'member')"
    )
    conn.execute(
        "INSERT INTO device (user_id, name, token_hash, created_at) VALUES (3, 'x', 'h3', 'x')"
    )
    conn.execute("DELETE FROM user WHERE id = 3")
    assert conn.execute("SELECT COUNT(*) FROM device WHERE user_id = 3").fetchone()[0] == 0


def test_backup_targets_from_before_0018_count_as_having_their_key_saved(tmp_path: Path) -> None:
    """0018 (issue 3): those targets use a password file their owner wrote and keeps."""
    db = tmp_path / "library.db"
    _make_v16_library(db)
    conn = open_database(db, backup_dir=tmp_path / "backups")
    rows = conn.execute("SELECT created_at, key_saved_at FROM backup_target").fetchall()
    assert [tuple(r) for r in rows] == [("2026-09-01", "2026-09-01")]


def _make_v20_library(db: Path, users: str) -> None:
    """A library just before 0022: sources added from the cloud (and an M1 folder) have no
    owner."""
    conn = sqlite3.connect(db)
    for number, sql in _migrations():
        if number <= 20:
            conn.executescript(f"BEGIN;{sql};PRAGMA user_version = {number};COMMIT;")
    conn.executescript(
        users
        + """
        INSERT INTO source (id, kind, label, root, owner_id, config_json) VALUES
            (1, 'rclone', 'MEGA', '/staging/1', NULL, '{"remote": "mega", "path": ""}'),
            (2, 'proton', 'Proton', '/staging/2', NULL, '{"provider": "proton"}'),
            (3, 'folder', 'Old', '/old', NULL, NULL);
        """
    )
    conn.close()


def _owners(conn: sqlite3.Connection) -> list[int | None]:
    return [r[0] for r in conn.execute("SELECT owner_id FROM source ORDER BY id")]


def test_ownerless_sources_go_to_the_first_enabled_admin(tmp_path: Path) -> None:
    """0022: a private mark only works on a source with an owner, so every source gets one.
    The first admin is the lowest id among admins who can still log in."""
    db = tmp_path / "library.db"
    _make_v20_library(
        db,
        """INSERT INTO user (id, username, display_name, password_hash, role, disabled) VALUES
            (1, 'lea', 'Lea', 'x', 'member', 0), (2, 'old', 'Old', 'x', 'admin', 1),
            (3, 'c', 'C', 'x', 'admin', 0), (4, 'p', 'P', 'x', 'admin', 0);
        INSERT INTO source (id, label, root, owner_id) VALUES (4, 'Leas', '/lea', 1);""",
    )
    conn = open_database(db, backup_dir=tmp_path / "backups")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _latest()
    assert _owners(conn) == [3, 3, 3, 1], "sources that had an owner keep it"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # access lists are not touched: who may see a source is a separate decision
    assert conn.execute("SELECT COUNT(*) FROM source_access").fetchone()[0] == 0


def test_ownerless_sources_wait_for_the_setup_when_there_is_no_admin(tmp_path: Path) -> None:
    """0022 on a library nobody has set up yet: nothing to assign; the first-run setup gives
    ownerless sources to the first admin, as it always did."""
    db = tmp_path / "library.db"
    _make_v20_library(db, "")
    conn = open_database(db, backup_dir=tmp_path / "backups")
    assert _owners(conn) == [None, None, None]
    admin = SqliteRepository(conn).add_first_admin("c", "C", "x")
    assert _owners(conn) == [admin.id] * 3
