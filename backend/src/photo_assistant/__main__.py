"""Command line.

python -m photo_assistant                    start the server (API + worker)
python -m photo_assistant import FOLDER      add FOLDER as a source (if new) and import it
python -m photo_assistant sources            list sources
"""

import argparse
import sys
from pathlib import Path

import uvicorn

from photo_assistant.api.logging_setup import configure_logging, shutdown_logging
from photo_assistant.api.main import create_app
from photo_assistant.api.services import build_services, overlaps
from photo_assistant.api.settings import get_settings
from photo_assistant.app.import_source import SourceUnavailableError
from photo_assistant.domain.model import ImportReport, Outcome
from photo_assistant.ports import ImportBusyError


def _serve() -> int:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
    return 0


def _check_folder(folder: Path, data_root: Path) -> str | None:
    if not folder.is_dir():
        return f"Not a folder: {folder}"
    if overlaps(folder, data_root):
        return "That folder contains, or is inside, the photo library itself."
    return None


def _print_report(run_id: int, report: ImportReport, show: int) -> None:
    s = report.summary()
    rows = [
        ("files seen", "files_seen"),
        ("imported", "imported"),
        ("duplicates", "duplicate"),
        ("already known", "already_known"),
        ("skipped", "skipped"),
        ("failed", "failed"),
        ("ignored", "ignored"),
    ]
    print()
    for label, key in rows:
        print(f"  {label:<14}{s[key]:>6}")
    print()
    for outcome in (Outcome.FAILED, Outcome.SKIPPED):
        items = [i for i in report.items if i.outcome is outcome]
        for item in items[:show]:
            name = (
                item.relative_path if item.relative_path.isprintable() else repr(item.relative_path)
            )
            print(f"  {outcome.value:<8} {name}: {item.reason}")
        if len(items) > show:
            print(f"  … and {len(items) - show} more {outcome.value} (see report #{run_id})")
    if report.message:
        print(f"\n{report.message}")


def _import(folder: Path, label: str | None, show: int) -> int:
    settings = get_settings()
    data_root = settings.data_root.expanduser()
    folder = folder.expanduser().resolve()
    problem = _check_folder(folder, data_root)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    configure_logging(data_root, "WARNING")
    services = build_services(settings)
    try:
        known = {s.root: s for s in services.repo.list_sources()}
        source = known.get(str(folder)) or services.repo.add_source(
            label or folder.name, str(folder)
        )
        print(f"Importing '{source.label}' from {folder} into {data_root} (source is read-only) …")
        try:
            run_id, report = services.importer.run(source.id)
        except (SourceUnavailableError, ImportBusyError) as exc:
            print(exc, file=sys.stderr)
            return 1
        _print_report(run_id, report, show)
        pending = services.repo.job_counts()["queued"]
        if pending:
            print(f"\nMaking {pending} full-size previews …")
            services.worker.run_until_idle()
        print(f"\nDone. Report #{run_id}. Library now holds {services.repo.count_assets()} photos.")
        return 0
    finally:
        services.close()
        shutdown_logging()


def _sources() -> int:
    services = build_services(get_settings())
    try:
        for s in services.repo.list_sources():
            state = "enabled " if s.enabled else "disabled"
            print(f"{s.id:>3}  {state}  {s.label:<24} {s.root}")
        return 0
    finally:
        services.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="photo_assistant")
    sub = parser.add_subparsers(dest="command")
    imp = sub.add_parser("import", help="import a folder (read-only) into the library")
    imp.add_argument("folder", type=Path)
    imp.add_argument("--label", help="name shown for this source (default: folder name)")
    imp.add_argument("--show", type=int, default=15, help="how many skips/failures to list")
    sub.add_parser("sources", help="list sources")
    args = parser.parse_args(argv)
    if args.command == "import":
        return _import(args.folder, args.label, args.show)
    if args.command == "sources":
        return _sources()
    return _serve()


if __name__ == "__main__":
    sys.exit(main())
