"""BackupEngine with restic (TECH_DECISIONS: Backup). Works with restic 0.14 (Debian bookworm) on.

- Always an argument list, never a shell: paths and remote names can't be misread.
- The password is only ever read by restic from ``--password-file``; RESTIC_* variables from
  our own environment are dropped so a stray one can't point a run at another repository.
- Snapshots use a fixed host name and tag, and forget/parent selection group by host+tags, not
  by absolute paths: after the library moves to the server, its snapshots continue the same
  history instead of starting a new one.
- Backups run with the data root as working directory and relative folder names, so the
  snapshot tree is ``/originals/...``: restoring a path is the path the database stores.
"""

import json
import os
import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from photo_assistant.adapters.tool_runner import ToolMissingError, ToolTimeoutError, run_tool
from photo_assistant.domain.backup import Retention, TargetKind, target_kind
from photo_assistant.ports.backup import (
    BackupError,
    BackupToolMissingError,
    IncompleteBackupError,
    PasswordFileError,
    RepositoryLockedError,
    RepositoryNotFoundError,
    RepositoryRef,
    SnapshotInfo,
    SnapshotSummary,
    WrongPasswordError,
)

SNAPSHOT_HOST = "photo-assistant"
SNAPSHOT_TAG = "photo-assistant"
_SUBSET = re.compile(r"^(\d{1,3}(\.\d+)?%|\d+/\d+|\d+[KMGT]?)$")
_TIME = re.compile(r"([^.Z+]+?)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)")
_DROPPED_ENV = frozenset(
    {
        "RESTIC_REPOSITORY",
        "RESTIC_REPOSITORY_FILE",
        "RESTIC_PASSWORD",
        "RESTIC_PASSWORD_FILE",
        "RESTIC_PASSWORD_COMMAND",
    }
)

# Questions about a repository are answered in seconds, even on a cloud remote; the commands
# that move photos may run for a day on the first backup of a large library.
QUICK_TIMEOUT = 300.0
LONG_TIMEOUT = 24 * 3600.0
_QUICK_COMMANDS = frozenset({"cat", "snapshots", "unlock", "stats"})

# restic >= 0.17 has distinct exit codes; older versions only say it on stderr.
_EXIT_NO_REPO, _EXIT_LOCKED, _EXIT_WRONG_PASSWORD, _EXIT_INCOMPLETE = 10, 11, 12, 3


def _tail(stderr: str) -> str:
    lines = [line for line in stderr.strip().splitlines() if not line.startswith("rclone: ")]
    return " ".join(lines[-3:])[:500] or "no details from restic"


def _duration(seconds: float) -> str:
    return f"{seconds / 3600:.0f} h" if seconds >= 3600 else f"{seconds:g} s"


def classify_failure(code: int, stderr: str, repo: RepositoryRef) -> BackupError:
    """Turn a restic exit into an error that says what happened and what to do."""
    text = stderr.lower()
    where = repo.location
    if code == _EXIT_WRONG_PASSWORD or "wrong password" in text:
        return WrongPasswordError(
            f"wrong password for the backup at {where}: check {repo.password_file}"
        )
    if "resolving password failed" in text or "password file" in text:
        return PasswordFileError(f"cannot read the password file {repo.password_file}")
    if code == _EXIT_NO_REPO or "is there a repository" in text:
        return RepositoryNotFoundError(
            f"no backup repository at {where}: is the disk plugged in / the server reachable?"
        )
    if code == _EXIT_INCOMPLETE:
        return IncompleteBackupError(
            f"some library files could not be read, the snapshot is incomplete: {_tail(stderr)}"
        )
    if code == _EXIT_LOCKED or "already locked" in text:
        return RepositoryLockedError(
            f"the backup at {where} is locked by another run; if none is running, "
            "run 'restic unlock' on it"
        )
    return BackupError(f"restic failed (exit {code}) for {where}: {_tail(stderr)}")


def parse_restic_time(value: str) -> datetime:
    """restic prints nanoseconds and 'Z'; Python wants at most microseconds."""
    match = _TIME.fullmatch(value)
    if match is None:
        raise BackupError(f"unexpected time from restic: {value!r}")
    main, frac, zone = match.groups()
    micro = f".{frac[:6]}" if frac else ""
    zone = "+00:00" if zone == "Z" else zone
    return datetime.fromisoformat(f"{main}{micro}{zone}").astimezone(UTC)


def _summary(stdout: str) -> SnapshotSummary:
    for line in reversed(stdout.strip().splitlines()):
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict) and message.get("message_type") == "summary":
            return SnapshotSummary(
                snapshot_id=str(message["snapshot_id"]),
                files_new=int(message.get("files_new", 0)),
                files_changed=int(message.get("files_changed", 0)),
                bytes_added=int(message.get("data_added", 0)),
                bytes_processed=int(message.get("total_bytes_processed", 0)),
            )
    raise BackupError("restic finished without a summary; the backup may be incomplete")


class ResticBackup:
    def __init__(
        self,
        binary: str = "restic",
        extra_env: Mapping[str, str] | None = None,
        cache_dir: Path | None = None,
        rclone_binary: str | None = None,
        rclone_config: Path | None = None,
        quick_timeout: float = QUICK_TIMEOUT,
        long_timeout: float = LONG_TIMEOUT,
    ) -> None:
        """``rclone_binary`` / ``rclone_config``: the rclone this app uses for its cloud
        sources; None leaves restic's own choice (``rclone`` on PATH, rclone's default file)."""
        self._binary = binary
        self._extra_env = dict(extra_env or {})
        self._cache_dir = cache_dir
        self._rclone_binary = rclone_binary
        self._quick_timeout = quick_timeout
        self._long_timeout = long_timeout
        if rclone_config is not None:
            self._extra_env.setdefault("RCLONE_CONFIG", str(rclone_config))

    # --- plumbing --------------------------------------------------------------------------

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in _DROPPED_ENV}
        env.update(self._extra_env)
        return env

    def _command(self, repo: RepositoryRef, args: Sequence[str]) -> list[str]:
        cmd = [self._binary, "--repo", repo.location, "--password-file", str(repo.password_file)]
        if self._cache_dir is not None:
            cmd += ["--cache-dir", str(self._cache_dir)]
        if self._rclone_binary and target_kind(repo.location) is TargetKind.RCLONE:
            # restic splits this value like a shell would: quote a path with spaces
            cmd += ["-o", f"rclone.program={shlex.quote(self._rclone_binary)}"]
        return [*cmd, *args]

    def _run(
        self, repo: RepositoryRef, args: Sequence[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        timeout = self._quick_timeout if args[0] in _QUICK_COMMANDS else self._long_timeout
        try:
            done = run_tool(self._command(repo, args), timeout=timeout, env=self._env(), cwd=cwd)
        except ToolMissingError as exc:
            raise BackupToolMissingError(
                f"'{self._binary}' is not installed: sudo apt install restic"
            ) from exc
        except ToolTimeoutError as exc:
            raise BackupError(
                f"restic did not answer within {_duration(timeout)} for {repo.location} "
                f"('{args[0]}') and was stopped; check the connection to the backup, then retry"
            ) from exc
        if done.returncode != 0:
            raise classify_failure(done.returncode, done.stderr, repo)
        return done

    # --- BackupEngine ----------------------------------------------------------------------

    def ensure_repository(self, repo: RepositoryRef) -> bool:
        try:
            self._run(repo, ["cat", "config"])
            return False
        except RepositoryNotFoundError:
            self._refuse_unmounted_disk(repo)
            self._run(repo, ["init"])
            return True

    @staticmethod
    def _refuse_unmounted_disk(repo: RepositoryRef) -> None:
        """Never create a repository where an unplugged disk should be.

        If /media/c/Backup is not mounted, "/media/c/Backup/photos" would silently be created
        on the laptop's own disk. We only create the last folder of the path."""
        if target_kind(repo.location) is TargetKind.LOCAL:
            parent = Path(repo.location).parent
            if not parent.is_dir():
                raise RepositoryNotFoundError(
                    f"{parent} does not exist: plug in / mount the backup disk, then retry"
                )

    def backup(self, repo: RepositoryRef, root: Path, folders: Sequence[str]) -> SnapshotSummary:
        present = [f for f in folders if (root / f).exists()]
        if not present:
            raise BackupError(f"nothing to back up in {root}")
        args = ["backup", "--json", "--quiet", "--host", SNAPSHOT_HOST, "--tag", SNAPSHOT_TAG]
        latest = self.latest_snapshot(repo)
        if latest is not None:
            args += ["--parent", latest.snapshot_id]  # fast: unchanged files are not re-read
        done = self._run(repo, [*args, "--", *present], cwd=root)
        return _summary(done.stdout)

    def forget(self, repo: RepositoryRef, retention: Retention) -> None:
        self._run(repo, ["unlock"])  # removes only stale locks (crashed runs), never live ones
        self._run(
            repo,
            [
                "forget",
                "--prune",
                "--tag",
                SNAPSHOT_TAG,
                "--group-by",
                "host,tags",
                "--keep-daily",
                str(retention.daily),
                "--keep-weekly",
                str(retention.weekly),
                "--keep-monthly",
                str(retention.monthly),
            ],
        )

    def check(self, repo: RepositoryRef, read_data_subset: str | None = None) -> None:
        args = ["check"]
        if read_data_subset is not None:
            if not _SUBSET.match(read_data_subset):
                raise BackupError(
                    f"bad read-data subset {read_data_subset!r}: use e.g. 5%, 1/10 or 500M"
                )
            args += ["--read-data-subset", read_data_subset]
        self._run(repo, args)

    def latest_snapshot(self, repo: RepositoryRef) -> SnapshotInfo | None:
        done = self._run(
            repo, ["snapshots", "--json", "--host", SNAPSHOT_HOST, "--tag", SNAPSHOT_TAG]
        )
        snapshots = json.loads(done.stdout or "[]") or []
        found = [SnapshotInfo(str(s["id"]), parse_restic_time(str(s["time"]))) for s in snapshots]
        return max(found, key=lambda s: s.time, default=None)

    def restore(
        self, repo: RepositoryRef, snapshot_id: str, paths: Sequence[str], target: Path
    ) -> None:
        if not paths:
            return  # restic would restore *everything* without an include
        includes = [arg for p in paths for arg in ("--include", "/" + p.lstrip("/"))]
        self._run(repo, ["restore", snapshot_id, "--target", str(target), *includes])

    def repository_size(self, repo: RepositoryRef) -> int:
        done = self._run(repo, ["stats", "--json", "--mode", "raw-data"])
        return int(json.loads(done.stdout)["total_size"])
