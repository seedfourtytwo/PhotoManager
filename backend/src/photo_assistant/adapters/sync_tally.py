"""The running count of one pull, whichever tool does it; its end is the SyncReport."""

from dataclasses import dataclass, field

from photo_assistant.ports.sync import SyncReport


@dataclass(slots=True)
class PullTally:
    copied: int = 0
    updated: int = 0
    unchanged: int = 0
    size: int = 0  # bytes transferred
    failed: int = 0  # the tool's own count, when it has one; else every entry of ``errors``
    errors: list[str] = field(default_factory=list)

    def report(self) -> SyncReport:
        return SyncReport(
            copied=self.copied,
            updated=self.updated,
            unchanged=self.unchanged,
            errors=self.failed or len(self.errors),
            bytes_transferred=self.size,
            error_messages=tuple(self.errors),
        )
