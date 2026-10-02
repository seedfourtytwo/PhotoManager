"""Repository-level latency of the library queries, on a COPY of a synthetic library.

    uv run python scripts/perf/bench_repo.py <library.db> [runs]

Prints the median (ms) per query and viewer. Synthetic libraries only (docs/PERFORMANCE.md).
Users 1-4 must be admin, member, member, guest (as in the QA libraries).
"""

import shutil
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.library_filter import AssetFilter


def _open(db: Path) -> SqliteRepository:
    try:  # this branch: the shared Database (per-thread readers)
        from photo_assistant.adapters.sqlite_repository import (
            Database,  # type: ignore[attr-defined]
        )

        return SqliteRepository(Database.open(db))
    except ImportError:  # older code, for "before" numbers
        return SqliteRepository(open_database(db))


def main() -> None:
    src, runs = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 7
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "library.db"
    shutil.copy(src, db)
    started = time.perf_counter()
    repo = _open(db)
    print(f"open+migrate {1000 * (time.perf_counter() - started):.0f} ms")

    def median(fn: Callable[[], object]) -> float:
        times = []
        for _ in range(runs):
            t = time.perf_counter()
            fn()
            times.append((time.perf_counter() - t) * 1000)
        return statistics.median(times)

    viewers = {
        "admin": Viewer(1, Role.ADMIN),
        "alice": Viewer(2, Role.MEMBER),
        "bob": Viewer(3, Role.MEMBER),
        "guest": Viewer(4, Role.GUEST),
    }
    ops: dict[str, Callable[[Viewer], object]] = {
        "timeline 200": lambda v: repo.list_views(v, AssetFilter(), 200),
        "year=2019": lambda v: repo.list_views(v, AssetFilter(year=2019), 200),
        "year+month": lambda v: repo.list_views(v, AssetFilter(year=2019, month=7), 200),
        "favourite": lambda v: repo.list_views(v, AssetFilter(favourite=True), 200),
        "source_id=2": lambda v: repo.list_views(v, AssetFilter(source_ids=(2,)), 200),
        "q=lisbon": lambda v: repo.list_views(v, AssetFilter(q="lisbon"), 200),
        "facets": lambda v: repo.facets(v, AssetFilter()),
        "calendar": lambda v: repo.calendar(v, AssetFilter()),
        "map": lambda v: repo.map_points(v, AssetFilter()),
    }
    print(f"{'op':14s} " + " ".join(f"{n:>8s}" for n in viewers))
    for name, op in ops.items():
        cells = " ".join(f"{median(lambda v=v, op=op: op(v)):8.1f}" for v in viewers.values())
        print(f"{name:14s} {cells}", flush=True)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
