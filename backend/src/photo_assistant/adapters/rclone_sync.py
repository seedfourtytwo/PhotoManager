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
from dataclasses import dataclass, field
from pathlib import Path

from photo_assistant.domain.media_types import IMPORTABLE_EXTENSIONS
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
    SyncReport,
)

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
    args = [binary, "copy", remote.target, str(staging)]
    args += ["--filter-from", str(filter_file), "--ignore-case"]
    args += ["--transfers", str(options.transfers), "--checkers", str(options.checkers)]
    args += ["--retries", str(options.retries)]
    if options.tpslimit > 0:
        args += ["--tpslimit", f"{options.tpslimit:g}"]
    args += ["--use-json-log", "--log-level", "INFO", "--stats", "24h"]
    if config_path is not None:
        args += ["--config", str(config_path)]
    return args


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


@dataclass(slots=True)
class _Tally:
    copied: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)

    def add(self, entry: dict[str, object]) -> None:
        msg = str(entry.get("msg", ""))
        if msg.startswith("Copied (new)"):
            self.copied += 1
        elif msg.startswith("Copied (replaced existing)"):
            self.updated += 1
        elif entry.get("level") == "error":
            obj = entry.get("object")
            self.errors.append(f"{obj}: {msg}" if obj else msg)
        stats = entry.get("stats")
        if isinstance(stats, dict):
            self.stats = stats

    def report(self) -> SyncReport:
        checks = _int(self.stats.get("checks"))
        return SyncReport(
            copied=self.copied,
            updated=self.updated,
            unchanged=max(checks - self.updated, 0),
            errors=_int(self.stats.get("errors")) or len(self.file_errors()),
            bytes_transferred=_int(self.stats.get("bytes")),
            error_messages=tuple(self.file_errors()),
        )

    def file_errors(self) -> list[str]:
        """Per-file problems, without rclone's "Attempt 1/3 failed" summaries."""
        return list(dict.fromkeys(e for e in self.errors if not e.startswith("Attempt ")))


def _int(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


def parse_log(stderr: str) -> _Tally:
    tally = _Tally()
    for line in stderr.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():  # rclone prints fatal setup errors as plain text
                tally.errors.append(line.strip().split(" ", 2)[-1])
            continue
        if isinstance(entry, dict):
            tally.add(entry)
    return tally


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
        if result.returncode == 0:
            return tally.report()
        if tally.copied or tally.updated:
            return tally.report()  # partial: keep what arrived, report the rest
        raise classify_failure(result.returncode, tally.errors, remote)

    def list_remotes(self) -> list[str]:
        """Names of the remotes set up in rclone's config (to catch typos early)."""
        args = [self._binary, "listremotes"]
        if self._config is not None:
            args += ["--config", str(self._config)]
        result = self._run(args, 30)
        return sorted(line.rstrip(":") for line in result.stdout.splitlines() if line.strip())

    def _run(self, args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
        try:
            return subprocess.run(  # an argument list, never a shell
                args, capture_output=True, text=True, timeout=timeout, check=False
            )
        except FileNotFoundError as exc:
            raise SyncError(
                "rclone is not installed on this machine (sudo apt install rclone)"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SyncError(
                f"the pull took longer than {timeout / 3600:.1f} h and was stopped; run it "
                "again to continue (files already pulled are kept)"
            ) from exc
