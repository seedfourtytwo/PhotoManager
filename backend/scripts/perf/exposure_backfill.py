"""Time the exposure backfill, and what reading the four exposure tags adds to an import.

    uv run python scripts/perf/exposure_backfill.py <folder of synthetic photos> [runs]

Imports the folder into a throw-away data root, then, ``runs`` times: forgets the stored
exposure values and runs the backfill jobs until idle. Also times the metadata read of every
library copy with and without the exposure tags. Synthetic photos only
(scripts/make_mock_library.py).
"""

import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

from photo_assistant.adapters import exiftool_reader
from photo_assistant.api.services import Services, build_services
from photo_assistant.api.settings import Settings
from photo_assistant.app.exposure_backfill import BATCH, EXPOSURE_BACKFILL_JOB

EXPOSURE_TAGS = ("EXIF:FNumber", "EXIF:ExposureTime", "EXIF:ISO", "EXIF:FocalLength")


def backfill_seconds(services: Services) -> float:
    with services.db.transaction() as conn:
        conn.execute(
            "UPDATE asset SET f_number = NULL, exposure_time = NULL, iso = NULL, "
            "focal_length = NULL"
        )
    services.repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    started = time.perf_counter()
    services.worker.run_until_idle(only={EXPOSURE_BACKFILL_JOB})
    return time.perf_counter() - started


def read_seconds(services: Services, paths: list[Path]) -> float:
    started = time.perf_counter()
    for at in range(0, len(paths), BATCH):
        services.exiftool.read_many(paths[at : at + BATCH])
    return time.perf_counter() - started


def main() -> None:
    folder = Path(sys.argv[1]).resolve()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 9
    root = Path(tempfile.mkdtemp())
    settings = Settings(data_root=root, min_free_gb=0, _env_file=None)  # type: ignore[call-arg]
    services = build_services(settings)
    try:
        source = services.repo.add_source("bench", str(folder))
        services.importer.run(source.id)
        count = services.repo.count_assets()
        filled = statistics.median(backfill_seconds(services) for _ in range(runs))
        with services.db.transaction() as conn:
            known = conn.execute("SELECT COUNT(*) FROM asset WHERE iso IS NOT NULL").fetchone()[0]
        print(
            f"backfill of {count} photos ({known} with settings): {filled:.2f} s"
            f" = {1000 * filled / count:.2f} ms/photo -> 10k: {filled / count * 10000:.0f} s"
        )

        paths = [services.store.absolute(p) for _, p in _library_paths(services)]
        all_tags = list(exiftool_reader._TAGS)
        with_tags, without = [], []
        for _ in range(runs):
            exiftool_reader._TAGS[:] = all_tags
            with_tags.append(read_seconds(services, paths))
            exiftool_reader._TAGS[:] = [t for t in all_tags if t not in EXPOSURE_TAGS]
            without.append(read_seconds(services, paths))
        exiftool_reader._TAGS[:] = all_tags
        a, b = statistics.median(without), statistics.median(with_tags)
        print(
            f"metadata read of {len(paths)} files: {1000 * a / len(paths):.2f} ms/photo without"
            f" the exposure tags, {1000 * b / len(paths):.2f} with"
        )
    finally:
        services.close()
        shutil.rmtree(root, ignore_errors=True)


def _library_paths(services: Services) -> list[tuple[int, str]]:
    with services.db.transaction() as conn:
        return [(int(r[0]), str(r[1])) for r in conn.execute("SELECT id, library_path FROM asset")]


if __name__ == "__main__":
    main()
