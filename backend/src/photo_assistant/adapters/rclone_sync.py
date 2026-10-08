"""SourceSync with rclone: ``rclone copy <remote>:<path> <staging>``, pull-only.

Why ``copy`` and nothing else:
- the remote is always the *source* of the copy, so rclone only reads it; no sync/move/delete
  command or flag is ever built (tested);
- without ``--ignore-existing``, a photo edited on the remote (new size or modification time)
  is refreshed in staging, and the importer then keeps both versions;
- ``copy`` never deletes in the destination, so photos removed from the remote stay in staging.

Credentials stay in rclone's own config file; we pass only the remote's name. Commands are
argument lists (never a shell), and a per-call filter file lets through photo extensions only.
"""

import json
import re
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

from photo_assistant.adapters.sync_tally import PullTally
from photo_assistant.adapters.tool_runner import ToolMissingError, ToolTimeoutError, run_tool
from photo_assistant.domain.media_types import IMPORTABLE_EXTENSIONS
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
    SyncReport,
    SyncToolMissingError,
)

_ANSWER_TIMEOUT = 30.0  # for questions about rclone's own config
_NOT_INSTALLED = "rclone is not installed on this machine (sudo apt install rclone)"

_AUTH = re.compile(
    r"couldn't login|login failed|unauthori[sz]ed|\b401\b|\b403\b|forbidden|invalid "
    r"(credentials|password|user|token)|authenticat|2fa|two.factor|token (expired|invalid)|"
    r"didn't find section in config file",
    re.IGNORECASE,
)
_RATE = re.compile(
    r"\b429\b|too many (requests|connections)|rate.?limit|eagain|etoomany|throttl|"
    r"quota exceeded|bandwidth limit",
    re.IGNORECASE,
)
_NOT_FOUND = re.compile(r"directory not found|object not found|not found|\b404\b", re.IGNORECASE)
_EXIT_DIR_NOT_FOUND = 3
_EXIT_FILE_NOT_FOUND = 4


def filter_rules(extensions: Iterable[str]) -> str:
    """rclone filter: skip AppleDouble ``._`` files, keep photo extensions, drop the rest."""
    lines = ["- ._*", *(f"+ *.{ext}" for ext in sorted(extensions)), "- *"]
    return "\n".join(lines) + "\n"


def build_command(
    binary: str,
    remote: RemoteConfig,
    staging: Path,
    filter_file: Path,
    options: SyncOptions,
    config_path: Path | None = None,
) -> list[str]:
    args = ["copy", remote.target, str(staging)]
    args += ["--filter-from", str(filter_file), "--ignore-case"]
    args += ["--transfers", str(options.transfers), "--checkers", str(options.checkers)]
    args += ["--retries", str(options.retries)]
    if options.tpslimit > 0:
        args += ["--tpslimit", f"{options.tpslimit:g}"]
    args += ["--use-json-log", "--log-level", "INFO", "--stats", "24h"]
    return rclone_command(binary, args, config_path)


def rclone_command(binary: str, args: list[str], config_path: Path | None) -> list[str]:
    """Any rclone call of this app: never waits at a keyboard for a config password (rclone
    then fails with its own explanation), and reads the config file the settings name."""
    command = [binary, *args, "--ask-password=false"]
    if config_path is not None:
        command += ["--config", str(config_path)]
    return command


def read_remotes(binary: str, config_path: Path | None) -> list[str]:
    """Names of the remotes in rclone's config; none when rclone refuses.
    Raises ToolMissingError / ToolTimeoutError."""
    command = rclone_command(binary, ["listremotes"], config_path)
    done = run_tool(command, timeout=_ANSWER_TIMEOUT)
    if done.returncode != 0:
        return []
    return sorted(line.rstrip(":") for line in done.stdout.splitlines() if line.strip())


def classify_failure(code: int, messages: list[str], remote: RemoteConfig) -> SyncError:
    """Turn rclone's exit code and error lines into one plain-language error."""
    text = "\n".join(messages)
    last = messages[-1] if messages else f"rclone exited with code {code}"
    name = remote.remote
    if "didn't find section in config file" in text:
        return SyncAuthError(
            f"the remote '{name}' is not set up on this machine: run 'rclone config' "
            "and create it with exactly that name (see the cloud sources guide)"
        )
    if _AUTH.search(text):
        return SyncAuthError(
            f"'{name}' refused the login: run 'rclone config reconnect {name}:' "
            f"or re-enter the password with 'rclone config' ({last})"
        )
    if _RATE.search(text):
        return SyncRateLimitedError(
            f"'{name}' is limiting requests right now; try again later ({last})"
        )
    if code in (_EXIT_DIR_NOT_FOUND, _EXIT_FILE_NOT_FOUND) or _NOT_FOUND.search(text):
        return SyncNotFoundError(f"folder '{remote.path or '/'}' not found on '{name}'")
    return SyncError(f"pulling from '{name}' failed: {last}")


def _count(tally: PullTally, entry: dict[str, object]) -> None:
    msg = str(entry.get("msg", ""))
    if msg.startswith("Copied (new)"):
        tally.copied += 1
    elif msg.startswith("Copied (replaced existing)"):
        tally.updated += 1
    elif entry.get("level") in ("error", "critical"):  # fatal setup errors are critical
        obj = entry.get("object")
        tally.errors.append(f"{obj}: {msg}" if obj else msg)


def _int(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


def parse_log(stderr: str) -> PullTally:
    """rclone's JSON log as a tally; ``errors`` holds every error line, summaries included."""
    tally = PullTally()
    stats: dict[str, object] = {}
    for line in stderr.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():  # rclone prints fatal setup errors as plain text
                tally.errors.append(line.strip().split(" ", 2)[-1])
            continue
        if isinstance(entry, dict):
            _count(tally, entry)
            if isinstance(entry.get("stats"), dict):
                stats = entry["stats"]  # the last one is the total
    tally.unchanged = max(_int(stats.get("checks")) - tally.updated, 0)
    tally.size = _int(stats.get("bytes"))
    tally.failed = _int(stats.get("errors"))
    return tally


def _report(tally: PullTally) -> SyncReport:
    """Per-file problems only, without rclone's "Attempt 1/3 failed" summaries."""
    tally.errors = list(dict.fromkeys(e for e in tally.errors if not e.startswith("Attempt ")))
    return tally.report()


class RcloneSync:
    def __init__(
        self,
        binary: str = "rclone",
        config_path: Path | None = None,
        extensions: Iterable[str] = IMPORTABLE_EXTENSIONS,
    ) -> None:
        self._binary = binary
        self._config = config_path
        self._filter = filter_rules(extensions)

    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pa-rclone-") as scratch:
            filter_file = Path(scratch) / "filter.txt"
            filter_file.write_text(self._filter)
            args = build_command(self._binary, remote, staging, filter_file, options, self._config)
            result = self._run(args, options.timeout_seconds)
        tally = parse_log(result.stderr)
        # a failed run that still brought something is partial: keep it, report the rest
        if result.returncode != 0 and not (tally.copied or tally.updated):
            raise classify_failure(result.returncode, tally.errors, remote)
        return _report(tally)

    def list_remotes(self) -> list[str]:
        """Names of the remotes set up in rclone's config (to catch typos early)."""
        try:
            return read_remotes(self._binary, self._config)
        except ToolMissingError as exc:
            raise SyncToolMissingError(_NOT_INSTALLED) from exc
        except ToolTimeoutError as exc:
            raise SyncError("rclone took too long to list its remotes; try again") from exc

    def _run(self, args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
        try:
            return run_tool(args, timeout=timeout)
        except ToolMissingError as exc:
            raise SyncToolMissingError(_NOT_INSTALLED) from exc
        except ToolTimeoutError as exc:
            raise SyncError(
                f"the pull took longer than {timeout / 3600:.1f} h and was stopped; run it "
                "again to continue (files already pulled are kept)"
            ) from exc
