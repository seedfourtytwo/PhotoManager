"""Ops commands: export-library, verify-library, doctor, backup.

Subcommands of ``python -m photo_assistant`` (the justfile calls them that way).
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from photo_assistant.adapters.sqlite_database import open_library_database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.adapters.system_probe import LocalSystemProbe
from photo_assistant.api.ops_services import (
    RcloneTool,
    build_backup_service,
    build_doctor_config,
    build_library_transfer,
)
from photo_assistant.api.settings import Settings, get_settings
from photo_assistant.app.backup import BackupService, UnknownTargetError
from photo_assistant.app.doctor import exit_code, render, run_doctor
from photo_assistant.app.library_transfer import ExportSummary, LibraryTransferError
from photo_assistant.domain.backup import BackupRun, NewBackupTarget, Retention, TargetStatus
from photo_assistant.domain.library_paths import DATABASE_FILE
from photo_assistant.domain.schedule import InvalidScheduleError
from photo_assistant.ports.library_files import CopyVerificationError, LibraryUnreadableError

COMMANDS = ("export-library", "verify-library", "doctor", "backup")
# argparse has no public name for the object add_subparsers() returns
type SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]


def human_bytes(size: int | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    raise AssertionError("unreachable")  # pragma: no cover


# --- parser ---------------------------------------------------------------------------------


def register(sub: SubParsers) -> None:
    """Add the ops subcommands to an existing ``add_subparsers()`` object."""
    export = sub.add_parser("export-library", help="copy the whole library to DEST, verified")
    export.add_argument("destination", type=Path)
    export.add_argument("--skip-derived", action="store_true", help="leave thumbnails out")
    verify = sub.add_parser("verify-library", help="check every photo's file and hash")
    verify.add_argument("root", type=Path, nargs="?", help="data root (default: PA_DATA_ROOT)")
    verify.add_argument("--skip-derived", action="store_true", help="don't check thumbnails")
    sub.add_parser("doctor", help="check this machine is ready to run the library")
    _register_backup(sub.add_parser("backup", help="backups: list, add, run, check, test"))


def _register_backup(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="backup_command", required=True)
    sub.add_parser("list", help="every target with its status")
    add = sub.add_parser("add", help="add a backup target")
    add.add_argument("label")
    add.add_argument("repository", help="/media/<you>/<disk>/photo-backup or rclone:remote:path")
    add.add_argument("--password-file", required=True, type=Path)
    add.add_argument("--schedule", default="daily 02:30")
    add.add_argument("--quiet-window", default=None, help="e.g. 22:00-06:00")
    retention = Retention()
    add.add_argument("--keep-daily", type=int, default=retention.daily)
    add.add_argument("--keep-weekly", type=int, default=retention.weekly)
    add.add_argument("--keep-monthly", type=int, default=retention.monthly)
    for name, text in (("run", "back up now"), ("enable", "enable"), ("disable", "disable")):
        sub.add_parser(name, help=text).add_argument("target_id", type=int)
    sub.add_parser("run-due", help="run every target whose schedule says so")
    check = sub.add_parser("check", help="verify the repository structure (and some data)")
    check.add_argument("target_id", type=int)
    check.add_argument("--read-data", default=None, help="also read this much data, e.g. 5%%")
    test = sub.add_parser("restore-test", help="restore a random sample and verify hashes")
    test.add_argument("target_id", type=int)
    test.add_argument("--sample", type=int, default=None)


# --- commands -------------------------------------------------------------------------------


def _print_export(summary: ExportSummary) -> None:
    print(f"\n  copied          {summary.copied:>8}  ({human_bytes(summary.bytes_copied)})")
    print(f"  already there   {summary.already_there:>8}")
    if summary.verify is not None:
        print("\n".join(summary.verify.lines()))


def _export(args: argparse.Namespace, settings: Settings) -> int:
    root = settings.data_root.expanduser()
    destination = args.destination.expanduser()
    print(f"Exporting {root} to {destination} (the library is only read) …")
    transfer = build_library_transfer()
    summary = transfer.export(
        root,
        destination,
        include_derived=not args.skip_derived,
        progress=lambda message: print(f"  {message}"),
    )
    _print_export(summary)
    if not summary.ok:
        print("\nThe copy has problems (above). Run the same command again to repair it.")
        return 1
    print(f"\nDone and verified. On the new machine set PA_DATA_ROOT={destination.resolve()}")
    print("(or the path you copy it to) and run: just verify-library")
    return 0


def _verify(args: argparse.Namespace, settings: Settings) -> int:
    root = (args.root or settings.data_root).expanduser()
    print(f"Verifying {root} …")
    report = build_library_transfer().verify(root, check_derived=not args.skip_derived)
    print("\n".join(report.lines()))
    print("\nEvery photo is present and intact." if report.ok else "\nProblems found (above).")
    return 0 if report.ok else 1


def _doctor(args: argparse.Namespace, settings: Settings) -> int:
    root = settings.data_root.expanduser()
    print(f"Photo Assistant doctor — data root {root}\n")
    checks = run_doctor(LocalSystemProbe(), build_doctor_config(root, settings.min_free_gb))
    print(render(checks))
    return exit_code(checks)


def _status_line(status: TargetStatus) -> str:
    t = status.target
    if not t.enabled:
        state = "disabled"
    elif status.failing:
        state = "FAILED"
    elif status.overdue:
        state = "OVERDUE"
    else:
        state = "ok"
    last = f"{status.last_success_at:%Y-%m-%d %H:%M}" if status.last_success_at else "never"
    upcoming = f"{status.next_run_at:%Y-%m-%d %H:%M}" if status.next_run_at else "-"
    return (
        f"{t.id:>3}  {state:<8} {t.label:<20} {t.schedule:<18} last ok {last:<16} "
        f"next {upcoming:<16} {human_bytes(status.repo_bytes):>9}  {t.repository}"
    )


def _print_run(run: BackupRun) -> int:
    print(f"{run.kind.value} {run.status.value}")
    if run.snapshot_id:
        print(f"  snapshot     {run.snapshot_id[:12]}")
    if run.bytes_added is not None:
        print(f"  new data     {human_bytes(run.bytes_added)} ({run.files_new} new files)")
    if run.repo_bytes is not None:
        print(f"  backup size  {human_bytes(run.repo_bytes)}")
    for text in (run.details, run.error):
        if text:
            print(f"  {text}")
    return 0 if run.status.value == "succeeded" else 1


def _backup_list(service: BackupService, args: argparse.Namespace) -> int:
    statuses = service.status()
    for status in statuses:
        print(_status_line(status))
        if status.last_run and status.last_run.error:
            print(f"       last error: {status.last_run.error}")
    if not statuses:
        print("No backup targets yet: see docs/guides/backups.md")
    return 0


def _backup_add(service: BackupService, args: argparse.Namespace) -> int:
    target = service.add_target(
        NewBackupTarget(
            label=args.label,
            repository=args.repository,
            password_file=str(args.password_file.expanduser().resolve()),
            schedule=args.schedule,
            quiet_window=args.quiet_window,
            retention=Retention(args.keep_daily, args.keep_weekly, args.keep_monthly),
        )
    )
    print(f"Added backup target {target.id} '{target.label}' ({target.schedule}).")
    print(f"Run it once now to create the repository: just backup run {target.id}")
    return 0


def _backup_toggle(enabled: bool) -> Callable[[BackupService, argparse.Namespace], int]:
    def toggle(service: BackupService, args: argparse.Namespace) -> int:
        service.set_enabled(args.target_id, enabled)
        print(f"Target {args.target_id} {'enabled' if enabled else 'disabled'}.")
        return 0

    return toggle


def _backup_run_due(service: BackupService, args: argparse.Namespace) -> int:
    runs = service.run_due()
    if not runs:
        print("Nothing is due.")
    return max((_print_run(r) for r in runs), default=0)


_BACKUP: dict[str, Callable[[BackupService, argparse.Namespace], int]] = {
    "list": _backup_list,
    "add": _backup_add,
    "run": lambda s, a: _print_run(s.run_now(a.target_id)),
    "run-due": _backup_run_due,
    "check": lambda s, a: _print_run(s.check(a.target_id, a.read_data)),
    "restore-test": lambda s, a: _print_run(s.restore_test(a.target_id, a.sample)),
    "enable": _backup_toggle(True),
    "disable": _backup_toggle(False),
}


def _backup(args: argparse.Namespace, settings: Settings) -> int:
    root = settings.data_root.expanduser()
    if not (root / DATABASE_FILE).is_file():
        print(f"No library at {root} yet: import some photos first.", file=sys.stderr)
        return 2
    db = open_library_database(root)
    repo = SqliteRepository(db)  # the same pieces as the server: one Database, every store
    service, _ = build_backup_service(
        root,
        settings.ops,
        db=db,
        rclone=RcloneTool(),
        source_roots=lambda: [Path(s.root) for s in repo.list_sources()],
    )
    try:
        return _BACKUP[args.backup_command](service, args)
    finally:
        db.close()


_HANDLERS: dict[str, Callable[[argparse.Namespace, Settings], int]] = {
    "export-library": _export,
    "verify-library": _verify,
    "doctor": _doctor,
    "backup": _backup,
}
_EXPECTED_ERRORS = (
    LibraryTransferError,
    LibraryUnreadableError,
    CopyVerificationError,
    UnknownTargetError,
    InvalidScheduleError,
    ValueError,
    OSError,
)


def dispatch(args: argparse.Namespace, settings: Settings | None = None) -> int | None:
    """Run an ops command; ``None`` if ``args.command`` is not one of ours."""
    handler = _HANDLERS.get(getattr(args, "command", None) or "")
    if handler is None:
        return None
    try:
        return handler(args, settings or get_settings())
    except _EXPECTED_ERRORS as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="photo_assistant")
    register(parser.add_subparsers(dest="command", required=True))
    result = dispatch(parser.parse_args(argv), settings)
    assert result is not None  # every registered command has a handler
    return result


if __name__ == "__main__":  # pragma: no cover - thin process entry point
    sys.exit(main())
