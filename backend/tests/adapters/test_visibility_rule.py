"""The per-photo visibility rule (C25) gives exactly what the set-based rule it replaced gave.

The old rule computed every grant of the whole library in one CTE; it is kept here as the
oracle. Random libraries (owners, access lists, albums, members, private marks, trash) are
checked for every viewer: same photos, same levels, live and in the trash.
"""

import random

import pytest

from photo_assistant.adapters.sqlite_library import visibility
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.domain.access import Role, Viewer

ORACLE = """WITH vis(asset_id, level) AS (
    SELECT g.asset_id, MIN(MAX(g.level), :vis_cap)
    FROM (
        SELECT x.asset_id AS asset_id, sa.level AS level, s.owner_id AS via_owner, 0 AS via_album
          FROM asset_source x JOIN source_access sa ON sa.source_id = x.source_id
          JOIN source s ON s.id = x.source_id
         WHERE sa.user_id IS NULL OR sa.user_id = :vis_uid
        UNION ALL
        SELECT x.asset_id, 3, s.owner_id, 0
          FROM asset_source x JOIN source s ON s.id = x.source_id WHERE s.owner_id = :vis_uid
        UNION ALL
        SELECT ai.asset_id, 1, NULL, 1
          FROM album_item ai JOIN album al ON al.id = ai.album_id
          LEFT JOIN album_member am ON am.album_id = al.id AND am.user_id = :vis_uid
         WHERE al.owner_id = :vis_uid OR am.user_id IS NOT NULL
        UNION ALL
        SELECT x.asset_id, 3, s.owner_id, 0
          FROM asset_source x JOIN source s ON s.id = x.source_id WHERE :vis_admin
        UNION ALL
        SELECT a0.id, 3, NULL, 0 FROM asset a0
         WHERE :vis_admin AND NOT EXISTS (SELECT 1 FROM asset_source x WHERE x.asset_id = a0.id)
    ) g
    JOIN asset a ON a.id = g.asset_id
    WHERE (a.private = 0 OR a.private_by = :vis_uid
           OR (g.via_album = 0 AND g.via_owner IS NOT a.private_by))
      AND (a.trashed_at IS NOT NULL) = :vis_trashed
    GROUP BY g.asset_id
) SELECT asset_id, level FROM vis"""

ROLES = [Role.ADMIN, Role.MEMBER, Role.MEMBER, Role.MEMBER, Role.GUEST]


def _people_and_sources(rng: random.Random, sql, users: list[int], sources: list[int]) -> None:  # type: ignore[no-untyped-def]
    for uid, role in zip(users, ROLES, strict=True):
        sql(
            "INSERT INTO user (id, username, display_name, password_hash, role) "
            "VALUES (?, ?, ?, 'x', ?)",
            (uid, f"u{uid}", f"U{uid}", role.value),
        )
    for sid in sources:
        sql(
            "INSERT INTO source (id, label, root, owner_id) VALUES (?, ?, ?, ?)",
            # None still exists: a library imported before its first account (0023 leaves
            # those; the setup assigns them), so the rule must keep handling it
            (sid, f"s{sid}", f"/s{sid}", rng.choice([None, *users])),
        )
        if rng.random() < 0.5:
            sql("INSERT INTO source_access VALUES (?, NULL, ?)", (sid, rng.randint(1, 3)))
        for uid in rng.sample(users, rng.randint(0, 3)):
            sql("INSERT INTO source_access VALUES (?, ?, ?)", (sid, uid, rng.randint(1, 3)))


def _photos(rng: random.Random, sql, users: list[int], sources: list[int]) -> None:  # type: ignore[no-untyped-def]
    for aid in range(1, 61):
        private = rng.random() < 0.3
        sql(
            """INSERT INTO asset (id, content_hash, kind, mime_type, byte_size, taken_at,
                   date_source, library_path, imported_at, private, private_by, trashed_at)
               VALUES (?, ?, 'photo', 'image/jpeg', 1, ?, 'exif', ?, 'x', ?, ?, ?)""",
            (
                aid,
                f"{aid:064x}",
                f"2020-01-01T00:{aid // 60:02d}:{aid % 60:02d}",
                f"originals/{aid}.jpg",
                int(private),
                rng.choice(users) if private else None,
                "2026-01-01" if rng.random() < 0.2 else None,
            ),
        )
        for n, sid in enumerate(rng.sample(sources, rng.randint(0, 3))):
            sql(
                "INSERT INTO asset_source (asset_id, source_id, relative_path) VALUES (?, ?, ?)",
                (aid, sid, f"{aid}-{n}.jpg"),
            )


def _albums(rng: random.Random, sql, users: list[int]) -> None:  # type: ignore[no-untyped-def]
    for album in range(1, 5):
        sql(
            "INSERT INTO album (id, owner_id, title, created_at, updated_at) "
            "VALUES (?, ?, 't', 'x', 'x')",
            (album, rng.choice(users)),
        )
        for pos, aid in enumerate(rng.sample(range(1, 61), 10)):
            sql("INSERT INTO album_item VALUES (?, ?, ?)", (album, aid, pos))
        for uid in rng.sample(users, 2):
            sql(
                "INSERT OR IGNORE INTO album_member VALUES (?, ?, ?)",
                (album, uid, rng.choice(["viewer", "editor"])),
            )


def _random_library(seed: int) -> SqliteRepository:
    rng = random.Random(seed)
    repo = SqliteRepository(Database.open(":memory:"))
    users, sources = list(range(1, len(ROLES) + 1)), list(range(1, 6))
    _people_and_sources(rng, repo._conn.execute, users, sources)
    _photos(rng, repo._conn.execute, users, sources)
    _albums(rng, repo._conn.execute, users)
    return repo


@pytest.mark.parametrize("seed", range(12))
def test_the_per_photo_rule_matches_the_set_based_rule(seed: int) -> None:
    repo = _random_library(seed)
    for uid, role in enumerate(ROLES, start=1):
        viewer = Viewer(uid, role)
        for trashed in (False, True):
            params = {
                "vis_uid": uid,
                "vis_admin": int(viewer.is_admin),
                "vis_cap": int(viewer.level_cap),
                "vis_trashed": int(trashed),
            }
            expected = {(r[0], r[1]) for r in repo._conn.execute(ORACLE, params)}
            visible, level, p = visibility(viewer, trashed=trashed)
            got = {
                (r[0], r[1])
                for r in repo._conn.execute(f"SELECT a.id, {level} FROM asset a WHERE {visible}", p)
            }
            assert got == expected, (seed, uid, role, trashed)
