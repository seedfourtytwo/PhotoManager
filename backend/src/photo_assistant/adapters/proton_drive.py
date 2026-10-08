"""SourceSync with Proton's own ``proton-drive`` CLI: list, then download what is new.

Pulling is read-only on Proton: only ``photo timeline``, ``photo download``, ``filesystem
list`` and ``filesystem download`` are ever built (tested). The one write offered here is
making a new, empty folder, for a backup copy to go in. The sign-in is the CLI's business (browser
login, session in the system keyring); this adapter never sees a password.

Proton has no "copy what changed" command, so the adapter keeps its own list of what it has
already fetched (node uids) in ``<staging>.proton.json`` beside the staging folder. Each batch
is downloaded into a working folder first and only then moved into staging under a name that
is free there, so a half-downloaded file never reaches the importer and nothing in staging is
ever overwritten. If the bookkeeping is lost, photos are fetched again rather than skipped:
the importer recognises a second copy by its content.
"""

import errno
import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from photo_assistant.adapters.sync_tally import PullTally
from photo_assistant.adapters.tool_runner import ToolMissingError, ToolTimeoutError, run_tool
from photo_assistant.domain.media_types import IMPORTABLE_EXTENSIONS
from photo_assistant.domain.remote_source import PROTON_PHOTOS, RemoteConfig
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncDiskFullError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncReport,
    SyncToolMissingError,
)

SIGN_IN = "proton-drive auth login"
# "failed to load session" is what v0.9.0 prints without a stored session; the others are
# guesses at how an expired one reads, so that it still lands on the sign-in hint.
_AUTH_HINTS = ("failed to load session", "auth login", "not logged in", "session expired")
_LIST_TIMEOUT = 600.0  # inside a pull (a long job): a big Drive takes minutes to list
_ASK_TIMEOUT = 30.0  # questions asked while a web request waits
_SLOW_ANSWER = "Proton Drive took too long to answer; try again later"
_OUT_OF_TIME = (
    "the pull took too long and was stopped; run it again to continue "
    "(photos already pulled are kept)"
)
# Whole batches failing in a row before failed batches stop being taken apart: when Proton is
# down, asking for every photo on its own only multiplies the failures.
_SPLIT_LIMIT = 3
_MAX_NAME_BYTES = 255  # what one file or folder name may take on Linux file systems
_DISK_FULL = (errno.ENOSPC, errno.EDQUOT)


class _PullStoppedError(SyncError):
    """Nothing more can be pulled now (out of time; its subclasses: tool gone, disk full):
    asking for the next photo cannot help. Out of time may pass: a later pull continues."""


class _ToolMissingError(_PullStoppedError, SyncToolMissingError):
    """The pull stops, and no later attempt can do better until the tool is installed."""


class _DiskFullError(_PullStoppedError, SyncDiskFullError):
    """The pull stops, and no later attempt can do better until space is freed."""


def find_binary(name: str) -> str:
    """Proton's installer puts the tool in ``~/.local/bin``, which a service's PATH often
    lacks: look there too."""
    if os.sep in name or shutil.which(name):
        return name
    local = Path.home() / ".local" / "bin" / name
    return str(local) if local.is_file() else name


@dataclass(frozen=True, slots=True)
class _Item:
    uid: str
    name: str
    remote: str  # the path the download command takes
    folder: PurePosixPath  # where it goes, relative to staging


@dataclass(frozen=True, slots=True)
class _Run:
    """One pull: how to download, where to, until when, what it has, and its running count."""

    verb: list[str]
    staging: Path
    prefix: str  # of the working folders beside staging
    deadline: float
    manifest: Path
    fetched: set[str]  # node uids already in staging
    tally: PullTally


def _name(node: dict[str, object]) -> str | None:
    """A node's name, or None when Proton could not decrypt it."""
    name = node.get("name")
    if isinstance(name, dict) and name.get("ok") and isinstance(name.get("value"), str):
        return str(name["value"])
    return None


def _is_photo(node: dict[str, object], name: str) -> bool:
    media = str(node.get("mediaType", "")).lower()
    if media.startswith("video/"):
        return False
    extension = PurePosixPath(name).suffix.lower().lstrip(".")
    return media.startswith("image/") or extension in IMPORTABLE_EXTENSIONS


def _usable(name: str) -> bool:
    """Whether a name can be one part of the path handed to the tool. ``.`` and ``..`` would
    make that path mean another place: for a file a folder, for a folder itself or its
    parent, which leaves the chosen folder or walks it in circles."""
    return "/" not in name and name not in (".", "..")


def _safe(name: str) -> str:
    """A folder name that stays inside staging whatever it is called on Proton."""
    cleaned = "".join("_" if c in "/\\" or ord(c) < 32 else c for c in name)
    cleaned = cleaned.encode()[:_MAX_NAME_BYTES].decode(errors="ignore")  # whole characters
    return "_" if cleaned.strip(". ") == "" else cleaned


def _disk_error(exc: OSError, where: Path) -> SyncError:
    if exc.errno in _DISK_FULL:
        return _DiskFullError(
            f"the disk holding {where} is full: free some space, then pull again "
            "(photos already pulled are kept)"
        )
    return SyncError(f"the pull could not write to {where}: {exc.strerror or exc}")


def _move_all(arrived: Sequence[Path], target: Path) -> int:
    """Move a downloaded batch into ``target`` under free names, all or nothing; its bytes."""
    target.mkdir(parents=True, exist_ok=True)
    placed: list[Path] = []
    size = 0
    try:
        for path in arrived:
            size += path.stat().st_size
            place = _free_name(target, path.name)
            path.replace(place)
            placed.append(place)
    except OSError:
        for place in placed:  # only what this call just put there: the batch is tried again
            place.unlink(missing_ok=True)
        raise
    return size


def _free_name(folder: Path, name: str) -> Path:
    target, n = folder / name, 1
    while target.exists():
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return target


def _chunks(items: Sequence[_Item], size: int) -> Iterator[Sequence[_Item]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class ProtonDrive:
    def __init__(self, binary: str = "proton-drive", batch_size: int = 20) -> None:
        self._binary = binary
        self._batch = max(batch_size, 1)

    def check(self) -> None:
        """Raises SyncAuthError when not signed in, SyncError when the tool is missing."""
        self.run(["filesystem", "list", "/"], _ASK_TIMEOUT)

    def folders(self, path: str) -> list[str]:
        """Names of the folders directly inside ``path``, for the folder picker."""
        names = [
            name
            for node in self._list(["filesystem", "list", path], path, _ASK_TIMEOUT)
            if node.get("type") == "folder" and (name := _name(node)) is not None
        ]
        return sorted(names, key=str.casefold)

    def create_folder(self, parent: str, name: str) -> str:
        """Make a new folder inside ``parent`` (a place in My files); its path."""
        self.run(["filesystem", "create-folder", parent, name, "--json"], _LIST_TIMEOUT, parent)
        return f"{parent}/{name}"

    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        try:
            return self._pull(remote, staging, options)
        except OSError as exc:  # this machine's disk, not Proton: say so in the import history
            raise _disk_error(exc, staging.parent) from exc

    def _pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        deadline = time.monotonic() + options.timeout_seconds
        tally = PullTally()
        if remote.path == PROTON_PHOTOS:
            items = self._timeline(tally)
            verb = ["photo", "download", "-c", "rename"]
        else:
            items = self._walk(remote.path, tally)
            verb = ["filesystem", "download", "-f", "rename", "-d", "merge"]
        staging.mkdir(parents=True, exist_ok=True)
        manifest = staging.parent / f"{staging.name}.proton.json"
        fetched = _read_fetched(manifest)
        wanted = [item for item in items if item.uid not in fetched]
        tally.unchanged = len(items) - len(wanted)
        prefix = f".{staging.name}.fetching-"
        for stale in staging.parent.glob(f"{prefix}*"):  # left by a pull that was killed
            shutil.rmtree(stale, ignore_errors=True)
        run = _Run(verb, staging, prefix, deadline, manifest, fetched, tally)
        listing_problems, failed_in_a_row = len(tally.errors), 0
        for batch in _batches(wanted, self._batch):
            before = tally.copied
            self._fetch(run, batch, split=failed_in_a_row < _SPLIT_LIMIT)
            failed_in_a_row = 0 if tally.copied > before else failed_in_a_row + 1
        if wanted and not tally.copied:
            raise SyncError(
                f"none of the {len(wanted)} new photos could be downloaded from Proton Drive "
                f"({tally.errors[listing_problems]})"
            )
        return tally.report()

    # --- what is there ----------------------------------------------------------------------

    def _timeline(self, tally: PullTally) -> list[_Item]:
        items = []
        for node in self._list(["photo", "timeline", "-d"], PROTON_PHOTOS):
            uid, name = str(node.get("uid", "")), _name(node)
            if name is None or not uid:
                tally.errors.append("a photo's name could not be read by Proton Drive")
            elif _is_photo(node, name):
                items.append(_Item(uid, name, f"{PROTON_PHOTOS}/{uid}", PurePosixPath()))
        return items

    def _walk(self, root: str, tally: PullTally) -> list[_Item]:
        items: list[_Item] = []
        pending = [(root, PurePosixPath())]
        while pending:
            path, local = pending.pop()
            try:
                nodes = self._list(["filesystem", "list", path], path)
            except SyncNotFoundError:
                if path == root:
                    raise
                tally.errors.append(f"{path}: the folder disappeared while it was being read")
                continue
            for node in nodes:
                uid, name = str(node.get("uid", "")), _name(node)
                if name is None or not uid or not _usable(name):
                    tally.errors.append(f"{path}: an item's name could not be read by Proton Drive")
                elif node.get("type") == "folder":
                    pending.append((f"{path}/{name}", local / _safe(name)))
                elif _is_photo(node, name):
                    items.append(_Item(uid, name, f"{path}/{name}", local))
        return items

    def _list(
        self, args: list[str], path: str, timeout: float = _LIST_TIMEOUT
    ) -> list[dict[str, object]]:
        out = self.run([*args, "--json"], timeout, path)
        try:
            nodes = json.loads(out)
        except json.JSONDecodeError as exc:
            raise SyncError("Proton Drive answered with something unreadable") from exc
        if not isinstance(nodes, list):
            raise SyncError("Proton Drive answered with something unreadable")
        return [node for node in nodes if isinstance(node, dict)]

    # --- fetching ---------------------------------------------------------------------------

    def _fetch(self, run: _Run, batch: Sequence[_Item], split: bool) -> None:
        """Download one batch into staging; what could not be fetched goes to the tally."""
        problem = self._download(run, batch)
        if problem is None:
            return
        if len(batch) == 1 or not split:
            run.tally.errors.extend(f"{item.folder / item.name}: {problem}" for item in batch)
            return
        for item in batch:  # which one failed? ask one at a time
            self._fetch(run, [item], split=False)

    def _download(self, run: _Run, batch: Sequence[_Item]) -> str | None:
        """None when every file of the batch is now in staging and remembered as fetched, else
        what went wrong (and nothing of the batch was kept)."""
        staging, tally = run.staging, run.tally
        work = Path(tempfile.mkdtemp(prefix=run.prefix, dir=staging.parent))
        try:
            remaining = run.deadline - time.monotonic()
            if remaining <= 0:
                raise _PullStoppedError(_OUT_OF_TIME)
            args = [*run.verb, *(item.remote for item in batch), str(work), "--json"]
            try:
                summary = json.loads(self.run(args, remaining, out_of_time=_OUT_OF_TIME))
            except (SyncAuthError, _PullStoppedError):
                raise
            except (SyncError, json.JSONDecodeError) as exc:
                return str(exc)
            arrived = sorted(p for p in work.iterdir() if p.is_file() and not p.is_symlink())
            failed = summary.get("failedItems", 0) if isinstance(summary, dict) else 1
            if failed or len(arrived) < len(batch):
                return "the download failed"
            target = staging.joinpath(*batch[0].folder.parts)
            try:
                tally.size += _move_all(arrived, target)
            except OSError as exc:
                if exc.errno in _DISK_FULL:
                    raise _disk_error(exc, staging) from exc
                return f"could not be saved on this machine ({exc.strerror or exc})"
            tally.copied += len(batch)
            # remembered as it lands: a pull cut off later must not fetch it a second time
            run.fetched.update(item.uid for item in batch)
            _write_fetched(run.manifest, run.fetched)
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def run(
        self, args: list[str], timeout: float, path: str = "", out_of_time: str = _SLOW_ANSWER
    ) -> str:
        """Run one command of the tool and return what it printed. ``path``: the remote place
        asked about, named in the error when Proton says it is not there."""
        try:
            result = run_tool(
                [self._binary, *args],
                timeout=timeout,
                env=os.environ | {"PROTON_DRIVE_LOG_LEVEL": "ERROR"},
            )
        except ToolMissingError as exc:
            raise _ToolMissingError(
                "Proton Drive's tool (proton-drive) is not installed on this machine"
            ) from exc
        except ToolTimeoutError as exc:
            raise _PullStoppedError(out_of_time) from exc
        if result.returncode == 0:
            return result.stdout
        text = result.stderr.strip() or f"proton-drive exited with code {result.returncode}"
        lowered = text.lower()
        if any(hint in lowered for hint in _AUTH_HINTS):
            raise SyncAuthError(
                f"Proton Drive is not signed in on this machine: run '{SIGN_IN}' and try again"
            )
        if "node not found" in lowered and path:
            raise SyncNotFoundError(f"folder '{path}' not found on Proton Drive")
        raise SyncError(f"Proton Drive: {text.splitlines()[-1]}")


def _batches(items: Sequence[_Item], size: int) -> Iterator[Sequence[_Item]]:
    """Batches of at most ``size`` that each land in one folder."""
    by_folder: dict[PurePosixPath, list[_Item]] = {}
    for item in items:
        by_folder.setdefault(item.folder, []).append(item)
    for group in by_folder.values():
        yield from _chunks(group, size)


def _read_fetched(manifest: Path) -> set[str]:
    try:
        data = json.loads(manifest.read_text())
        return {uid for uid in data["fetched"] if isinstance(uid, str)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()  # lost bookkeeping: fetch again, never skip


def _write_fetched(manifest: Path, fetched: set[str]) -> None:
    draft = manifest.with_name(manifest.name + ".new")
    with draft.open("w") as handle:
        handle.write(json.dumps({"fetched": sorted(fetched)}))
        handle.flush()
        os.fsync(handle.fileno())  # on the disk before it replaces the list it extends
    draft.replace(manifest)
