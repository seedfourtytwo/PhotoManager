"""RepositoryMirror on Proton Drive: an off-site copy of a local backup repository.

The repository is restic's: already encrypted, its files never change once written and are
only ever added or (by prune) removed. So mirroring is: upload what Proton lacks, then delete
from Proton what the repository no longer has. Uploading comes first, so the copy never
misses a file a snapshot needs.

Only ever writes inside ``<remote folder>/<repository name>`` (tested), and never to the
local repository. What was last known to be on Proton is kept in a small state file, so an
ordinary run needs no listing; without it the copy on Proton is walked instead.
"""

import json
from pathlib import Path, PurePosixPath

from photo_assistant.adapters.proton_drive import ProtonDrive
from photo_assistant.domain.remote_source import PROTON_PHOTOS, RemoteConfig, RemoteConfigError
from photo_assistant.ports.backup import MirrorError, MirrorReport, MirrorSignInError
from photo_assistant.ports.sync import SyncAuthError, SyncError, SyncNotFoundError

_UPLOAD = ["filesystem", "upload", "-f", "skip", "-d", "merge", "-t"]
_QUICK = 600.0


class ProtonMirror:
    def __init__(self, drive: ProtonDrive, upload_timeout: float = 24 * 3600.0) -> None:
        self._drive = drive
        self._upload_timeout = upload_timeout

    def mirror(self, repository: Path, remote_folder: str, state_file: Path) -> MirrorReport:
        try:
            if remote_folder == PROTON_PHOTOS:
                raise RemoteConfigError
            RemoteConfig.proton(remote_folder)
        except RemoteConfigError as exc:
            raise MirrorError("the copy must go in a folder in My files on Proton Drive") from exc
        if not repository.is_dir():
            raise MirrorError(f"backup folder not found: {repository}")
        copy = f"{remote_folder}/{repository.name}"
        local = {p.relative_to(repository).as_posix() for p in repository.rglob("*") if p.is_file()}
        try:
            known = _read_state(state_file, copy)
            if known is None:
                known = self._walk(copy)
            sent = self._upload(repository, remote_folder)
            stale = sorted(known - local)
            removed = sum(self._remove(copy, relative) for relative in stale)
        except SyncAuthError as exc:
            raise MirrorSignInError(str(exc)) from exc
        except SyncNotFoundError as exc:
            raise MirrorError(str(exc)) from exc
        except SyncError as exc:
            raise MirrorError(f"the copy on Proton Drive failed: {exc}") from exc
        _write_state(state_file, copy, local)
        return MirrorReport(uploaded=len(local - known), removed=removed, bytes_sent=sent)

    def _upload(self, repository: Path, remote_folder: str) -> int:
        out = self._drive.run(
            [*_UPLOAD, str(repository), remote_folder, "--json"],
            self._upload_timeout,
            remote_folder,
        )
        try:
            summary = json.loads(out)
            failed, sent = int(summary["failedItems"]), int(summary["transferredBytes"])
        except (ValueError, KeyError, TypeError) as exc:
            raise MirrorError("Proton Drive answered the upload with something unreadable") from exc
        if failed:
            raise MirrorError(
                f"{failed} file{'' if failed == 1 else 's'} could not be uploaded to Proton "
                "Drive; the next backup tries again"
            )
        return sent

    def _walk(self, copy: str) -> set[str]:
        """Relative paths of the files in the copy on Proton (empty when it isn't there yet)."""
        found: set[str] = set()
        pending = [PurePosixPath()]
        while pending:
            folder = pending.pop()
            path = copy if folder == PurePosixPath() else f"{copy}/{folder}"
            try:
                nodes = json.loads(
                    self._drive.run(["filesystem", "list", path, "--json"], _QUICK, path)
                )
            except SyncNotFoundError:
                continue
            except json.JSONDecodeError as exc:
                raise MirrorError("Proton Drive answered with something unreadable") from exc
            for node in nodes:
                name = node.get("name", {})
                if not name.get("ok") or "/" in str(name.get("value")):
                    raise MirrorError(f"a name in {path} on Proton Drive could not be read")
                child = folder / str(name["value"])
                if node.get("type") == "folder":
                    pending.append(child)
                else:
                    found.add(child.as_posix())
        return found

    def _remove(self, copy: str, relative: str) -> int:
        """Delete one file of the copy for good; 0 when it was gone already."""
        parts = PurePosixPath(relative).parts
        if not parts or relative.startswith("/") or ".." in parts:
            raise MirrorError(f"refusing to remove '{relative}': not a file of the copy")
        path = f"{copy}/{relative}"
        try:
            uid = json.loads(self._drive.run(["filesystem", "info", path, "--json"], _QUICK, path))[
                "uid"
            ]
        except SyncNotFoundError:
            return 0
        except (ValueError, KeyError, TypeError) as exc:
            raise MirrorError("Proton Drive answered with something unreadable") from exc
        self._drive.run(["filesystem", "trash", path, "--json"], _QUICK, path)
        # by uid, not by name: exactly the file just trashed, whatever else is in the trash
        self._drive.run(["filesystem", "delete", f"/trash/{uid}", "--json"], _QUICK, path)
        return 1


def _read_state(state_file: Path, copy: str) -> set[str] | None:
    """What the last mirror left on Proton at ``copy``; None when that isn't known."""
    try:
        data = json.loads(state_file.read_text())
        if data["copy"] != copy:
            return None
        return {str(name) for name in data["files"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_state(state_file: Path, copy: str, files: set[str]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    draft = state_file.with_name(state_file.name + ".new")
    draft.write_text(json.dumps({"copy": copy, "files": sorted(files)}))
    draft.replace(state_file)
