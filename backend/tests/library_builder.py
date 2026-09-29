"""Build a real library from the synthetic fixtures with the real importer and services."""

from pathlib import Path

from photo_assistant.api.services import build_services
from photo_assistant.api.settings import Settings


def settings_for(data_root: Path) -> Settings:
    return Settings(data_root=data_root, worker_enabled=False, min_free_gb=0)


def build_library(data_root: Path, source: Path) -> None:
    """Import ``source`` (read-only) into a new library at ``data_root``, previews included."""
    services = build_services(settings_for(data_root))
    try:
        imported = services.repo.add_source("Fixtures", str(source))
        services.importer.run(imported.id)
        services.worker.run_until_idle()
    finally:
        services.close()


def import_more(data_root: Path, source: Path) -> None:
    services = build_services(settings_for(data_root))
    try:
        known = {s.root: s for s in services.repo.list_sources()}
        src = known.get(str(source)) or services.repo.add_source(source.name, str(source))
        services.importer.run(src.id)
        services.worker.run_until_idle()
    finally:
        services.close()
