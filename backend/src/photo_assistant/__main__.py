"""Command line.

python -m photo_assistant                    start the server (API + worker)
python -m photo_assistant import FOLDER      add FOLDER as a source (if new) and import it
python -m photo_assistant sources            list sources
python -m photo_assistant create-user NAME [--role admin|member|guest]
                                             create an account (prompts for the PIN)
python -m photo_assistant set-pin NAME       give an account a new PIN (forgotten, or locked)
python -m photo_assistant doctor             check this machine is ready
python -m photo_assistant export-library DEST / verify-library [ROOT]
python -m photo_assistant backup list|add|run|check|restore-test …
python -m photo_assistant ml-backfill        queue ML analysis of everything (after just models)
python -m photo_assistant exposure-backfill  queue reading aperture, shutter, ISO and focal
                                             length for photos imported before they were kept
"""

import argparse
import getpass
import sys
from pathlib import Path

import uvicorn

from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.api import cli_ops
from photo_assistant.api.cli_command import Command
from photo_assistant.api.logging_setup import configure_logging, shutdown_logging
from photo_assistant.api.main import create_app
from photo_assistant.api.services import build_services
from photo_assistant.api.settings import get_settings
from photo_assistant.app.accounts import AccountError
from photo_assistant.app.enrich import GEOCODE_JOB, GROUP_JOB
from photo_assistant.app.exposure_backfill import EXPOSURE_BACKFILL_JOB
from photo_assistant.app.import_source import PREVIEW_JOB, SourceUnavailableError
from photo_assistant.domain.access import PIN_LENGTH, Role
from photo_assistant.domain.model import ImportReport, Outcome
from photo_assistant.ports import ImportBusyError

# What an import itself queues. Everything else in the queue (backups, scans of other
# sources, ML) belongs to the server and stays there.
_IMPORT_JOBS = frozenset({PREVIEW_JOB, GEOCODE_JOB, GROUP_JOB})


def _serve() -> int:
    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies,
    )
    return 0


def _check_folder(folder: Path, data_root: Path) -> str | None:
    if not folder.is_dir():
        return f"Not a folder: {folder}"
    if DiskLibraryStore(data_root).overlaps(folder):
        return "That folder contains, or is inside, the photo library itself."
    return None


def _safe(text: str) -> str:
    """Never let a file name put control codes on the terminal."""
    return text if text.isprintable() else repr(text)


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
            print(f"  {outcome.value:<8} {_safe(item.relative_path)}: {_safe(item.reason or '')}")
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
        # nobody is logged in on the command line: the folder belongs to the first admin
        services.accounts.give_ownerless_sources_to_first_admin()
        print(f"Importing '{source.label}' from {folder} into {data_root} (source is read-only) …")
        try:
            run_id, report = services.importer.run(source.id)
        except (SourceUnavailableError, ImportBusyError) as exc:
            print(exc, file=sys.stderr)
            return 1
        _print_report(run_id, report, show)
        services.enqueue_enrichment()
        queued = services.repo.list_jobs("queued")
        pending = sum(job["kind"] in _IMPORT_JOBS for job in queued)
        if pending:
            print(f"\nMaking {pending} full-size previews …")
            services.worker.run_until_idle(only=_IMPORT_JOBS)
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


def _ask_pin(username: str) -> str | None:
    pin = getpass.getpass(f"PIN for {username} ({PIN_LENGTH} digits): ")
    if getpass.getpass("Repeat the PIN: ") != pin:
        print("The PINs do not match.", file=sys.stderr)
        return None
    return pin


def _create_user(username: str, role: Role, display_name: str | None) -> int:
    pin = _ask_pin(username)
    if pin is None:
        return 2
    services = build_services(get_settings())
    try:
        services.accounts.create_user(username, display_name or username, pin, role)
    except AccountError as exc:
        print(exc, file=sys.stderr)
        return 2
    finally:
        services.close()
    print(f"Created {role.value} '{username}'.")
    return 0


def _set_pin(username: str) -> int:
    pin = _ask_pin(username)
    if pin is None:
        return 2
    services = build_services(get_settings())
    try:
        user = services.accounts.set_pin(username, pin)
    except AccountError as exc:
        print(exc, file=sys.stderr)
        return 2
    finally:
        services.close()
    print(
        f"New PIN set for '{user.username}'. Their other logins and phone tokens are ended, "
        "and the account is unlocked."
    )
    return 0


def _ml_backfill() -> int:
    services = build_services(get_settings())
    try:
        queued = services.ml.backfill()
        status = services.ml.status()
    finally:
        services.close()
    print(f"Queued {queued} analysis jobs; the server's worker runs them.")
    for name, model in status.items():
        print(f"  {name:<6} {'ready' if model.ready else 'missing'}: {model.detail}")
    return 0


def _exposure_backfill() -> int:
    services = build_services(get_settings())
    try:
        queued = services.repo.enqueue_once(EXPOSURE_BACKFILL_JOB)
    finally:
        services.close()
    if queued is None:
        print("Already waiting in the queue; the server's worker runs it.")
    else:
        print(
            "Queued: the server's worker reads aperture, shutter, ISO and focal length from "
            "the library copy of every photo that has none yet."
        )
    return 0


def _import_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("folder", type=Path)
    parser.add_argument("--label", help="name shown for this source (default: folder name)")
    parser.add_argument("--show", type=int, default=15, help="how many skips/failures to list")


def _create_user_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("username")
    parser.add_argument("--role", type=Role, choices=list(Role), default=Role.MEMBER)
    parser.add_argument("--display-name")


def _username_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("username")


# THE table of sub-commands, in the order ``--help`` lists them. A new command is one more
# entry here (the ops ones have theirs in api/cli_ops.py). Without a sub-command: the server.
COMMANDS: tuple[Command, ...] = (
    Command(
        "import",
        "import a folder (read-only) into the library",
        lambda args: _import(args.folder, args.label, args.show),
        _import_arguments,
    ),
    Command("sources", "list sources", lambda args: _sources()),
    Command(
        "create-user",
        "create an account (asks for the PIN)",
        lambda args: _create_user(args.username, args.role, args.display_name),
        _create_user_arguments,
    ),
    Command(
        "set-pin",
        "give an account a new PIN (asks for it); this also unlocks it",
        lambda args: _set_pin(args.username),
        _username_argument,
    ),
    Command(
        "ml-backfill",
        "queue ML analysis of every photo not analysed yet",
        lambda args: _ml_backfill(),
    ),
    Command(
        "exposure-backfill",
        "queue reading the exposure settings of photos imported before they were kept",
        lambda args: _exposure_backfill(),
    ),
    *cli_ops.COMMANDS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photo_assistant")
    sub = parser.add_subparsers(dest="command")
    for command in COMMANDS:
        command.arguments(sub.add_parser(command.name, help=command.help))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        return _serve()
    return next(c for c in COMMANDS if c.name == args.command).run(args)


if __name__ == "__main__":
    sys.exit(main())
