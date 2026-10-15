"""Latency of Home (GET /api/home's work) and the person and pinned filters, on a synthetic
library of database rows only (no image files), built in a temporary folder.

    uv run python scripts/perf/bench_home.py [photos] [runs]

Four viewers as in the QA libraries (admin, two members, a guest) over six sources with mixed
access; ~15 years of photos in bursts and trips, 70 % with a place, 8 % with a guessed date,
2 % imported in the last week, favourites, and faces of 20 people on 30 % of the photos. The
calendar, the other read over the whole visible library, is timed beside it for comparison.
"""

import functools
import random
import shutil
import statistics
import struct
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.home import home_page
from photo_assistant.app.people import People
from photo_assistant.domain.access import Level, Role, SourceAccess, Viewer
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.rediscover import rediscover
from photo_assistant.domain.years import years

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
CITIES = [
    ("France", "Brittany", "Carnac"),
    ("France", "Ile-de-France", "Paris"),
    ("Portugal", "Lisboa", "Lisbon"),
    ("Italy", "Lazio", "Rome"),
    ("France", "Nouvelle-Aquitaine", "Sarlat"),
    ("Spain", "Catalonia", "Barcelona"),
    ("United States", "California", "Montara"),
    ("France", "Auvergne-Rhone-Alpes", "Chamonix"),
]
PEOPLE = 20


def _sources(repo: SqliteRepository) -> list[int]:
    admin = repo.add_user("admin", "A", "h", Role.ADMIN).id
    alice = repo.add_user("alice", "Alice", "h", Role.MEMBER).id
    bob = repo.add_user("bob", "Bob", "h", Role.MEMBER).id
    repo.add_user("guest", "G", "h", Role.GUEST)
    alice_too = SourceAccess(None, ((alice, Level.VIEW),))
    return [
        repo.add_source("Phone", "/s/phone", admin).id,
        repo.add_source("Old disk", "/s/old", admin, access=SourceAccess(Level.VIEW)).id,
        repo.add_source("Alice", "/s/alice", alice, access=SourceAccess(None)).id,
        repo.add_source("Bob", "/s/bob", bob, access=alice_too).id,
        repo.add_source("Scans", "/s/scans", admin).id,
        repo.add_source("Camera", "/s/camera", admin, access=SourceAccess(Level.DOWNLOAD)).id,
    ]


def _photos(n: int, sources: list[int], rng: random.Random) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    taken = datetime(2011, 1, 1, 9)
    while len(rows) < n:
        taken += timedelta(days=rng.choice([0.5, 1, 3, 7, 14, 30]))
        place = rng.randint(1, len(CITIES)) if rng.random() < 0.7 else None
        source = rng.choice(sources)
        for _ in range(min(rng.randint(3, 60), n - len(rows))):
            taken += timedelta(minutes=rng.randint(1, 600))
            i = len(rows) + 1
            recent = rng.random() < 0.02
            imported = NOW - timedelta(days=rng.random() * 6 if recent else 60)
            dated = "file_mtime" if rng.random() < 0.08 else "exif"
            rows.append(
                (i, f"{i:064x}", taken.isoformat(), dated, imported.isoformat(), source, place)
            )
    return rows


def build(path: Path, n: int, seed: int = 7) -> None:
    rng = random.Random(seed)
    db = Database.open(path)
    sources = _sources(SqliteRepository(db))
    conn = db.writer
    conn.executemany("INSERT INTO place (country, region, city) VALUES (?, ?, ?)", CITIES)
    photos = _photos(n, sources, rng)
    conn.executemany(
        """INSERT INTO asset (id, content_hash, kind, byte_size, width, height, library_path,
               taken_at, date_source, imported_at, first_source_id, place_id)
           VALUES (?, ?, 'photo', 1000, 4000, 3000, ?, ?, ?, ?, ?, ?)""",
        [(p[0], p[1], f"o/{p[0]}", *p[2:]) for p in photos],
    )
    conn.executemany(
        "INSERT INTO asset_source (asset_id, source_id, relative_path) VALUES (?, ?, ?)",
        [(p[0], p[5], f"{p[0]}.jpg") for p in photos],
    )
    for user in (1, 2, 3):
        conn.executemany(
            "INSERT INTO user_asset (user_id, asset_id, favourite) VALUES (?, ?, 1)",
            [(user, a) for a in rng.sample(range(1, n + 1), n // 50)],
        )
    conn.executemany(
        "INSERT INTO person (id, name) VALUES (?, ?)",
        [(p, f"P{p}" if p < 15 else None) for p in range(1, PEOPLE + 1)],
    )
    blob = struct.pack("<4f", 1, 0, 0, 0)
    conn.executemany(
        """INSERT INTO face (asset_id, model, box_x, box_y, box_w, box_h, score,
               landmarks_json, dim, embedding, person_id)
           VALUES (?, 'm', 0.1, 0.1, 0.2, 0.2, 0.9, '[]', 4, ?, ?)""",
        [(a, blob, rng.randint(1, PEOPLE)) for a in range(1, n + 1) if rng.random() < 0.3],
    )
    conn.commit()
    conn.execute("ANALYZE")
    db.close()


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 9
    tmp = Path(tempfile.mkdtemp())
    build(tmp / "library.db", n)
    db = Database.open(tmp / "library.db")
    repo, people = SqliteRepository(db), People(SqliteMlStore(db))
    viewers = {
        "admin": Viewer(1, Role.ADMIN),
        "alice": Viewer(2, Role.MEMBER),
        "bob": Viewer(3, Role.MEMBER),
        "guest": Viewer(4, Role.GUEST),
    }

    moments = {v: repo.moments(v) for v in viewers.values()}

    def median(fn: Callable[[], object]) -> float:
        times = []
        for _ in range(runs):
            started = time.perf_counter()
            fn()
            times.append((time.perf_counter() - started) * 1000)
        return statistics.median(times)

    ops: dict[str, Callable[[Viewer], object]] = {
        "home": lambda v: home_page(repo, people, v, NOW),
        "  moments": repo.moments,
        "  arrivals": lambda v: repo.arrivals(v, NOW - timedelta(days=7), 12),
        "  rediscover": lambda v: rediscover(moments[v], NOW.date()),
        "  years": lambda v: years(moments[v], NOW.date()),
        "person_id=1,2": lambda v: repo.list_views(v, AssetFilter(person_ids=(1, 2)), 200),
        "pinned": lambda v: repo.list_views(v, AssetFilter(pinned=True), 200),
        "timeline 200": lambda v: repo.list_views(v, AssetFilter(), 200),
        "calendar": lambda v: repo.calendar(v, AssetFilter()),
    }
    print(f"{n} photos, ms, median of {runs}")
    print(f"{'op':14s} " + " ".join(f"{name:>8s}" for name in viewers))
    for name, op in ops.items():
        cells = " ".join(f"{median(functools.partial(op, v)):8.1f}" for v in viewers.values())
        print(f"{name:14s} {cells}", flush=True)
    db.close()
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
