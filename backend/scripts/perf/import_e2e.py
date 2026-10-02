"""Import a folder and render every preview with the background lanes; wall time until idle.

    uv run python scripts/perf/import_e2e.py <folder of synthetic photos>

Uses a throw-away data root. Synthetic photos only (scripts/make_mock_library.py).
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path

from photo_assistant.api.services import build_services
from photo_assistant.api.settings import Settings

WATCHED = ("scan_source", "preview")


def main() -> None:
    folder = Path(sys.argv[1]).resolve()
    root = Path(tempfile.mkdtemp())
    settings = Settings(  # type: ignore[call-arg]
        data_root=root,
        min_free_gb=0,
        worker_poll_seconds=0.05,
        argon2_time_cost=1,
        argon2_memory_kib=64,
        _env_file=None,
    )
    services = build_services(settings)
    source = services.repo.add_source("bench", str(folder))
    started = time.perf_counter()
    services.repo.enqueue("scan_source", {"source_id": source.id})
    services.worker.start()

    def busy() -> list[dict[str, object]]:
        return [
            j
            for j in services.repo.list_jobs()
            if j["status"] in ("queued", "running") and j["kind"] in WATCHED
        ]

    time.sleep(0.5)
    scan_done = None
    while pending := busy():
        if scan_done is None and not any(j["kind"] == "scan_source" for j in pending):
            scan_done = time.perf_counter() - started
        time.sleep(0.2)
    total = time.perf_counter() - started
    count = max(services.repo.count_assets(), 1)
    services.worker.stop()
    lane = scan_done or 0.0
    print(f"import lane finished after {lane:.1f} s ({1000 * lane / count:.0f} ms/photo)")
    per_photo = total / count
    print(
        f"{count} photos with previews: {total:.1f} s = {1000 * per_photo:.0f} ms/photo"
        f" -> 10k: {per_photo * 10000 / 60:.0f} min"
    )
    services.close()
    shutil.rmtree(root)


if __name__ == "__main__":
    main()
