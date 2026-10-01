"""What ``just doctor`` asks of the machine. The adapter probes; app/doctor.py judges."""

from pathlib import Path
from typing import Protocol


class SystemProbe(Protocol):
    def tool_version(self, tool: str) -> str | None:
        """Version of a command-line tool (exiftool, restic, rclone); None if not installed."""
        ...

    def libvips_version(self) -> str | None: ...

    def decode_error(self, sample: Path) -> str | None:
        """Render the sample with the real renderer; the error text, or None if it worked."""
        ...

    def free_bytes(self, folder: Path) -> int:
        """Free space on the disk that holds ``folder`` (or its nearest existing parent)."""
        ...

    def writable_error(self, folder: Path) -> str | None:
        """Why we can't write there, or None. A missing folder is checked via its parent."""
        ...

    def database_integrity(self, database: Path) -> str:
        """``"ok"``, or what ``PRAGMA integrity_check`` found."""
        ...

    def has_models(self, folder: Path) -> bool: ...
