"""Seed a throw-away library for the E2E suite against the real backend (synthetic photos only).

    uv run python scripts/make_mock_library.py /tmp/e2e-src --count 150 --size 800
    uv run python scripts/e2e_seed.py /tmp/e2e-src /tmp/e2e-data --scans /tmp/e2e-scans

Imports the three mock source folders, then writes two snapshots the test-mode server resets
to (``POST /__test/reset``): ``none`` (photos, no accounts: the first-run screen) and ``seed``
(the same people, access, albums and failed job as the web mock in ``web/mock-api/data.ts``).
``--scans`` writes a folder for the "admin adds a folder" journey: six new photos, a duplicate,
a broken JPEG and a video.

Never point it at a real library: it refuses a data root that already exists.
"""

import argparse
import random
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from photo_assistant.adapters.sqlite_snapshot import SqliteSnapshotter
from photo_assistant.api.services import Services, build_services
from photo_assistant.api.settings import Settings
from photo_assistant.domain.access import AlbumRole, Level, Role

SOURCES = [("phone", "Phone"), ("old-hdd", "Old hard disk"), ("partner", "Partner")]
USERS = [  # as web/mock-api/data.ts SEED_USERS
    ("admin", "C", Role.ADMIN, "correct horse"),
    ("partner", "Partner", Role.MEMBER, "battery staple"),
    ("guest", "Guest", Role.GUEST, "guest password"),
]
DORDOGNE = (44.89, 1.22)
BRITTANY = (47.75, -3.37)


def near(conn: sqlite3.Connection, where: tuple[float, float], limit: int) -> list[int]:
    lat, lon = where
    rows = conn.execute(
        """SELECT id FROM asset WHERE abs(latitude - ?) < 0.3 AND abs(longitude - ?) < 0.3
           ORDER BY taken_at LIMIT ?""",
        (lat, lon, limit),
    ).fetchall()
    return [int(r[0]) for r in rows]


def import_sources(services: Services, sources: Path) -> dict[str, int]:
    ids = {}
    for folder, label in SOURCES:
        source = services.repo.add_source(label, str((sources / folder).resolve()))
        _, report = services.importer.run(source.id)
        print(f"  {label:<14} {report.summary()}")
        ids[folder] = source.id
    services.enqueue_enrichment()
    done = services.worker.run_until_idle()
    print(f"  ran {done} follow-up jobs (previews, places, groups, ML)")
    return ids


def seed_people(services: Services, sources: dict[str, int], db: Path) -> None:
    repo, accounts, now = services.repo, services.accounts, services.clock.now()
    user_ids = {}
    for username, name, role, password in USERS:
        user_ids[username] = accounts.create_user(username, name, password, role).id
    partner = user_ids["partner"]
    repo.set_access(sources["old-hdd"], Level.VIEW, [(partner, Level.DOWNLOAD)])
    repo.set_source_owner(sources["partner"], partner)
    repo.set_access(sources["partner"], None, [(partner, Level.EDIT)])

    conn = sqlite3.connect(db)
    summers = near(conn, DORDOGNE, 24)
    brittany = near(conn, BRITTANY, 12)
    every_23rd = [r[0] for r in conn.execute("SELECT id FROM asset ORDER BY id")][::23]
    conn.close()
    album = repo.create_album(user_ids["admin"], "Summers at the house", "Dordogne, every August", now)
    repo.add_album_items(album, summers, None, now)
    repo.set_album_members(album, [(partner, AlbumRole.EDITOR)], now)
    other = repo.create_album(partner, "Brittany", "", now)
    repo.add_album_items(other, brittany, None, now)
    repo.set_user_state(user_ids["admin"], every_23rd, favourite=True)

    # one failed preview, as in the mock (retrying it succeeds: the file is fine)
    job = repo.enqueue("preview", {"asset_id": summers[0] if summers else 1})
    claimed = repo.claim_next_job(now)
    assert claimed is not None and claimed.id == job
    repo.fail_job(job, "libvips could not decode the file (truncated JPEG)", retry=False)


def write_scans(scans: Path, sources: Path) -> None:
    scans.mkdir(parents=True)
    rng = random.Random(7)
    for i in range(6):
        image = Image.new("RGB", (640, 480), tuple(rng.randrange(256) for _ in range(3)))
        draw = ImageDraw.Draw(image)
        draw.ellipse((100 + i * 20, 100, 300, 300), fill=(240, 220, 120))
        exif = Image.Exif()
        exif[0x0132] = datetime(2026, 9, 20 + i % 5, 10 + i).strftime("%Y:%m:%d %H:%M:%S")
        image.save(scans / f"scan_{i + 1:03d}.jpg", quality=85, exif=exif)
    first_phone = sorted((sources / "phone").rglob("*.[jJ][pP][gG]"))[0]
    shutil.copy(first_phone, scans / f"copy of {first_phone.name}")
    # a JPEG header and then noise: libvips decodes a merely truncated JPEG (greyed bottom)
    (scans / "broken.jpg").write_bytes(b"\xff\xd8\xff\xe0" + rng.randbytes(2000))
    (scans / "IMG_0501.MOV").write_bytes(b"\x00\x00\x00\x18ftypqt  " + bytes(64))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sources", type=Path, help="output of make_mock_library.py")
    parser.add_argument("data", type=Path, help="new data root for the test server")
    parser.add_argument("--scans", type=Path, help="also write the 'add a folder' test folder")
    args = parser.parse_args()
    if args.data.exists():
        print(f"{args.data} exists: give a new folder (this never touches a real library)")
        return 2
    settings = Settings(data_root=args.data, worker_enabled=False, min_free_gb=0)
    services = build_services(settings)
    snapshots = args.data / "test-snapshots"
    try:
        print("Importing the mock sources …")
        sources = import_sources(services, args.sources)
        SqliteSnapshotter(args.data / "library.db").snapshot(snapshots / "none.db")
        seed_people(services, sources, args.data / "library.db")
        SqliteSnapshotter(args.data / "library.db").snapshot(snapshots / "seed.db")
    finally:
        services.close()
    if args.scans:
        write_scans(args.scans, args.sources)
    print(f"Snapshots 'none' and 'seed' in {snapshots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
