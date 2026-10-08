"""SourceSync: mirror a remote source into a local staging folder, read-only on the remote.

The staging folder is then imported like any local folder. A pull only ever *adds or
refreshes* files in staging: nothing is written to, moved on or deleted from the remote, and
files that disappear from the remote stay in staging (the library keeps them anyway).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.errors import NotFoundError, UnavailableError
from photo_assistant.domain.remote_source import RemoteConfig


class SyncError(RuntimeError):
    """The pull failed; the message says what happened and what to do.

    By itself not a DomainError: what makes a pull fail may pass (the network, a slow or
    throttling provider, an answer that took too long), and the worker retries a job that
    fails for it. Met while answering a request it is a 503 (``api/main.py``).

    A cause that waiting does not fix is one of the subclasses below that are a DomainError
    as well: the family gives the HTTP status, and the worker fails the job at once."""


class SyncRateLimitedError(SyncError):
    """The provider is throttling us (MEGA does this under heavy use). It may pass."""


class SyncAuthError(SyncError, UnavailableError):
    """The remote refused the login (or the remote isn't set up in rclone): until someone
    signs in or sets it up, every pull fails the same way."""


class SyncNotFoundError(SyncError, NotFoundError):
    """The folder doesn't exist on the remote."""


class SyncToolMissingError(SyncError, UnavailableError):
    """The tool that pulls (rclone, proton-drive) is not installed. Waiting does not install it."""


class SyncUnsupportedError(SyncError, UnavailableError):
    """A source of a provider this version has no tool for."""


class SyncDiskFullError(SyncError, UnavailableError):
    """This machine's disk is full: nothing more can be pulled until space is freed."""


@dataclass(frozen=True, slots=True)
class SyncOptions:
    # MEGA-safe defaults: MEGA may block an account that makes too many requests.
    tpslimit: float = 4.0
    transfers: int = 2
    checkers: int = 4
    retries: int = 3
    timeout_seconds: float = 6 * 3600.0


@dataclass(frozen=True, slots=True)
class SyncReport:
    copied: int = 0  # new files in staging
    updated: int = 0  # changed on the remote, refreshed in staging
    unchanged: int = 0
    errors: int = 0
    bytes_transferred: int = 0
    error_messages: tuple[str, ...] = field(default_factory=tuple)

    @property
    def partial(self) -> bool:
        return self.errors > 0


class SourceSync(Protocol):
    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        """Mirror ``remote`` into ``staging`` (created if missing). Raises SyncError subclasses
        when nothing could be pulled; a partial pull returns a report with ``errors``."""
        ...


class RemoteSourceStore(Protocol):
    """Where remote sources keep their settings (the source row's ``config_json``)."""

    def add_remote_source(
        self, label: str, config: RemoteConfig, staging_root: Path, owner_id: int
    ) -> int:
        """Create a source of the provider's kind, owned by ``owner_id`` (the admin adding it),
        whose root is ``staging_root/<id>``; its id."""
        ...

    def remote_config(self, source_id: int) -> RemoteConfig | None:
        """None if the source isn't a remote one. Raises RemoteConfigError if unusable."""
        ...

    def set_root(self, source_id: int, root: str) -> None: ...
