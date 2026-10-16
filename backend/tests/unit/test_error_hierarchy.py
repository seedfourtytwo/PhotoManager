"""The rule of ENGINEERING_RULES §4, kept true: every exception class in the package is a
DomainError (the one handler answers it; the worker does not retry it), or it is listed here
with the reason it is not.

Adding an error class? Derive it from a family in ``domain/errors.py``. Only when it must stay
out (the worker should retry it, or it never leaves the code that raises it) add it below, with
why.
"""

import importlib
import inspect
import pkgutil

import photo_assistant
from photo_assistant.domain.errors import DomainError

MAY_PASS = "may pass by waiting: the worker retries a job that fails for it"
SIGNAL = "a signal between two parts of the code, caught there; no route or job ever sees it"
COMMAND_LINE = "raised and reported by a command-line operation only (export, verify)"

NOT_DOMAIN_ERRORS = {
    # --- retried by the worker ---------------------------------------------------------------
    "ports.sync.SyncError": MAY_PASS + " (network, a slow provider); the app answers it 503",
    "ports.sync.SyncRateLimitedError": "a SyncError: the provider throttles, " + MAY_PASS,
    "adapters.proton_drive._PullStoppedError": "a SyncError: out of time, " + MAY_PASS,
    "ports.backup.BackupError": MAY_PASS + "; BackupService records it on the backup run",
    "ports.backup.RepositoryLockedError": "a BackupError: another restic holds the lock",
    "ports.backup.RepositoryNotFoundError": "a BackupError: the disk may only be unplugged",
    "ports.backup.WrongPasswordError": "a BackupError, recorded on the run; no route answers it",
    "ports.backup.IncompleteBackupError": "a BackupError: files unreadable this time",
    "ports.backup.MirrorError": "a BackupError: the copy to Proton Drive failed this time",
    "ports.backup.MirrorSignInError": "a MirrorError, recorded on the run until the user signs in",
    "ports.ai.AIUnavailableError": MAY_PASS + " (the AI server is slow or down)",
    "ports.ai.AIUnreachableError": MAY_PASS + " (an AIUnavailableError: no answer at all)",
    "adapters.ollama_guard.NotLocalError": "an AIUnreachableError: a setting that points off "
    "this machine stops the app at start; later refusals make jobs retry, never fail a photo",
    "ports.ImportBusyError": "another import holds the library: the worker puts the job back",
    # --- never reach a route or a job ----------------------------------------------------------
    "adapters.tool_runner.ToolTimeoutError": SIGNAL + " (adapters raise their own 'too slow')",
    "adapters.tool_runner.ToolMissingError": SIGNAL + " (adapters raise their own 'not installed')",
    "adapters.filesystem.HashMismatchError": SIGNAL + " (the importer reports that file as failed)",
    "ports.DuplicateAssetError": SIGNAL + " (the importer links the existing photo)",
    "ports.upload.UploadTooLargeError": SIGNAL + " (the receiver reports that file as rejected)",
    "ports.accounts.UsernameTakenError": SIGNAL + " (Accounts raises NameTakenError)",
    "ports.accounts.NotFirstUserError": SIGNAL + " (Accounts raises AlreadySetUpError)",
    "ports.accounts.NoActiveAdminError": SIGNAL + " (Accounts raises LastAdminError)",
    "adapters.ollama_ai._BadOutputError": SIGNAL + " (one retry, then AIUnavailableError)",
    "domain.album_plan.PlanFormatError": SIGNAL + " (the AI adapter's answer check)",
    "domain.look.LookError": SIGNAL + " (Accounts raises InvalidLookError)",
    "domain.library_paths.InvalidLibraryPathError": "a broken invariant (a bug), not a request",
    "ports.printing.PrintRenderError": "the print engine failed on a job we built: a bug, a 500",
    "adapters.sqlite_database.NewerDatabaseError": "stops the app at start; no request yet",
    # --- the command line ------------------------------------------------------------------------
    "app.library_transfer.LibraryTransferError": COMMAND_LINE,
    "ports.library_files.CopyVerificationError": COMMAND_LINE,
    "ports.library_files.LibraryUnreadableError": COMMAND_LINE,
}


def _exception_classes() -> dict[str, type[BaseException]]:
    """Every exception class defined under ``photo_assistant``, by its dotted name without
    the package."""
    found: dict[str, type[BaseException]] = {}
    for info in pkgutil.walk_packages(photo_assistant.__path__, "photo_assistant."):
        if info.name.endswith("__main__"):  # importing it would run the command line
            continue
        module = importlib.import_module(info.name)
        for cls in vars(module).values():
            if (
                inspect.isclass(cls)
                and issubclass(cls, BaseException)
                and cls.__module__ == info.name
            ):
                dotted = f"{cls.__module__}.{cls.__qualname__}"
                found[dotted.removeprefix("photo_assistant.")] = cls
    return found


def test_every_exception_class_is_a_domain_error_or_listed_with_a_reason() -> None:
    classes = _exception_classes()
    assert len(classes) > 50, "the walk found the package"
    outside = {name for name, cls in classes.items() if not issubclass(cls, DomainError)}
    unlisted = sorted(outside - NOT_DOMAIN_ERRORS.keys())
    assert unlisted == [], (
        "derive these from a family in domain/errors.py, or list them in NOT_DOMAIN_ERRORS "
        "with the reason"
    )


def test_the_list_of_exceptions_names_only_classes_that_are_outside_the_hierarchy() -> None:
    classes = _exception_classes()
    gone = sorted(NOT_DOMAIN_ERRORS.keys() - classes.keys())
    assert gone == [], "renamed or removed: take them off the list"
    inside = sorted(n for n in NOT_DOMAIN_ERRORS if issubclass(classes[n], DomainError))
    assert inside == [], "a DomainError needs no exception: take it off the list"
    assert all(reason.strip() for reason in NOT_DOMAIN_ERRORS.values())


def test_every_domain_error_carries_an_http_error_status() -> None:
    for name, cls in _exception_classes().items():
        if issubclass(cls, DomainError):
            assert isinstance(cls.status, int) and 400 <= cls.status < 600, name
