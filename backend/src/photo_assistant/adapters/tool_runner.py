"""The one way adapters start an external program (restic, rclone, proton-drive, exiftool).

Always an argument list, never a shell. The program gets no keyboard (a password prompt would
block a job lane for hours) and must finish within a timeout the caller chooses. Its exit code
and output come back as they are: what a failure means is the calling adapter's business.
"""

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


class ToolMissingError(Exception):
    """The program is not installed, or not where the settings say."""


class ToolTimeoutError(Exception):
    """The program did not finish in time and was stopped."""


def run_tool(
    command: Sequence[str],
    *,
    timeout: float,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """``env`` None: this process's environment. Raises ToolMissingError, ToolTimeoutError."""
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise ToolMissingError(f"'{command[0]}' is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolTimeoutError(f"'{command[0]}' did not finish within {timeout:g} s") from exc
