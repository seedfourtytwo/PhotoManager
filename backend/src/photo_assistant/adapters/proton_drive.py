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

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from photo_assistant.domain.media_types import IMPORTABLE_EXTENSIONS
from photo_assistant.domain.remote_source import PROTON_PHOTOS, RemoteConfig
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncReport,
)

SIGN_IN = "proton-drive auth login"
# "failed to load session" is what v0.9.0 prints without a stored session; the others are
# guesses at how an expired one reads, so that it still lands on the sign-in hint.
_AUTH_HINTS = ("failed to load session", "auth login", "not logged in", "session expired")
_LIST_TIMEOUT = 600.0


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


@dataclass(slots=True)
class _Tally:
    copied: int = 0
    unchanged: int = 0
    size: int = 0
    errors: list[str] = field(default_factory=list)

    def report(self) -> SyncReport:
        return SyncReport(
            copied=self.copied,
            unchanged=self.unchanged,
            errors=len(self.errors),
            bytes_transferred=self.size,
            error_messages=tuple(self.errors),
        )


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


def _safe(name: str) -> str:
    """A folder name that stays inside staging whatever it is called on Proton."""
    cleaned = "".join("_" if c in "/\\" or ord(c) < 32 else c for c in name)
    return "_" if cleaned.strip(". ") == "" else cleaned


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
        self.run(["filesystem", "list", "/"], _LIST_TIMEOUT)

    def folders(self, path: str) -> list[str]:
        """Names of the folders directly inside ``path``, for the folder picker."""
        names = [
            name
            for node in self._list(["filesystem", "list", path], path)
            if node.get("type") == "folder" and (name := _name(node)) is not None
        ]
        return sorted(names, key=str.casefold)

    def create_folder(self, parent: str, name: str) -> str:
        """Make a new folder inside ``parent`` (a place in My files); its path."""
        self.run(["filesystem", "create-folder", parent, name, "--json"], _LIST_TIMEOUT, parent)
        return f"{parent}/{name}"

    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        deadline = time.monotonic() + options.timeout_seconds
        tally = _Tally()
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
        for batch in _batches(wanted, self._batch):
            done = self._fetch(verb, batch, staging, prefix, deadline, tally)
            if done:
                fetched.update(done)
                _write_fetched(manifest, fetched)
        return tally.report()

    # --- what is there ----------------------------------------------------------------------

    def _timeline(self, tally: _Tally) -> list[_Item]:
        items = []
        for node in self._list(["photo", "timeline", "-d"], PROTON_PHOTOS):
            uid, name = str(node.get("uid", "")), _name(node)
            if name is None or not uid:
                tally.errors.append("a photo's name could not be read by Proton Drive")
            elif _is_photo(node, name):
                items.append(_Item(uid, name, f"{PROTON_PHOTOS}/{uid}", PurePosixPath()))
        return items

    def _walk(self, root: str, tally: _Tally) -> list[_Item]:
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
                if name is None or not uid or "/" in name:
                    tally.errors.append(f"{path}: an item's name could not be read by Proton Drive")
                elif node.get("type") == "folder":
                    pending.append((f"{path}/{name}", local / _safe(name)))
                elif _is_photo(node, name):
                    items.append(_Item(uid, name, f"{path}/{name}", local))
        return items

    def _list(self, args: list[str], path: str) -> list[dict[str, object]]:
        out = self.run([*args, "--json"], _LIST_TIMEOUT, path)
        try:
            nodes = json.loads(out)
        except json.JSONDecodeError as exc:
            raise SyncError("Proton Drive answered with something unreadable") from exc
        if not isinstance(nodes, list):
            raise SyncError("Proton Drive answered with something unreadable")
        return [node for node in nodes if isinstance(node, dict)]

    # --- fetching ---------------------------------------------------------------------------

    def _fetch(
        self,
        verb: list[str],
        batch: Sequence[_Item],
        staging: Path,
        prefix: str,
        deadline: float,
        tally: _Tally,
    ) -> list[str]:
        """Download one batch and move it into staging; the uids that arrived."""
        problem = self._download(verb, batch, staging, prefix, deadline, tally)
        if problem is None:
            return [item.uid for item in batch]
        if len(batch) == 1:
            tally.errors.append(f"{batch[0].folder / batch[0].name}: {problem}")
            return []
        done: list[str] = []  # which one failed? ask one at a time
        for item in batch:
            done += self._fetch(verb, [item], staging, prefix, deadline, tally)
        return done

    def _download(
        self,
        verb: list[str],
        batch: Sequence[_Item],
        staging: Path,
        prefix: str,
        deadline: float,
        tally: _Tally,
    ) -> str | None:
        """None when every file of the batch is now in staging, else what went wrong (and
        nothing of the batch was kept)."""
        work = Path(tempfile.mkdtemp(prefix=prefix, dir=staging.parent))
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SyncError(
                    "the pull took too long and was stopped; run it again to continue "
                    "(photos already pulled are kept)"
                )
            args = [*verb, *(item.remote for item in batch), str(work), "--json"]
            try:
                summary = json.loads(self.run(args, remaining))
            except SyncAuthError:
                raise
            except (SyncError, json.JSONDecodeError) as exc:
                return str(exc)
            arrived = sorted(p for p in work.iterdir() if p.is_file() and not p.is_symlink())
            failed = summary.get("failedItems", 0) if isinstance(summary, dict) else 1
            if failed or len(arrived) < len(batch):
                return "the download failed"
            target = staging.joinpath(*batch[0].folder.parts)
            target.mkdir(parents=True, exist_ok=True)
            for path in arrived:
                tally.size += path.stat().st_size
                path.replace(_free_name(target, path.name))
            tally.copied += len(batch)
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def run(self, args: list[str], timeout: float, path: str = "") -> str:
        """Run one command of the tool and return what it printed. ``path``: the remote place
        asked about, named in the error when Proton says it is not there."""
        try:
            result = subprocess.run(  # an argument list, never a shell
                [self._binary, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=os.environ | {"PROTON_DRIVE_LOG_LEVEL": "ERROR"},
            )
        except FileNotFoundError as exc:
            raise SyncError(
                "Proton Drive's tool (proton-drive) is not installed on this machine"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SyncError("Proton Drive took too long to answer; try again later") from exc
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
    draft.write_text(json.dumps({"fetched": sorted(fetched)}))
    draft.replace(manifest)
