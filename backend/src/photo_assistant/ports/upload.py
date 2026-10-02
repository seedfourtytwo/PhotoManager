"""Ports for uploads from phones and browsers into a user's inbox source."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.model import Source


class UploadTooLargeError(ValueError):
    """The file is bigger than the upload size limit."""


@dataclass(frozen=True, slots=True)
class SpooledUpload:
    """A fully received upload in the temp folder, hashed while it streamed in."""

    path: Path
    content_hash: str
    byte_size: int
    head: bytes  # first bytes, for sniffing the format


class SpoolWriter(Protocol):
    def write(self, chunk: bytes) -> None:
        """Append; raises UploadTooLargeError once the limit is passed (and discards)."""
        ...

    def finish(self) -> SpooledUpload: ...

    def discard(self) -> None: ...


class UploadSpool(Protocol):
    def open(self, max_bytes: int) -> SpoolWriter: ...

    def commit(self, upload: SpooledUpload, folder: Path, names: Iterator[str]) -> Path:
        """Move atomically into ``folder`` under the first free name; never overwrites."""
        ...

    def discard(self, upload: SpooledUpload) -> None: ...


class LibraryIndex(Protocol):
    """The two things uploads need from the library (the Repository satisfies it)."""

    def hashes_present(self, viewer: Viewer, hashes: Sequence[str]) -> dict[str, int | None]:
        """Of ``hashes``, the ones this viewer already has: the photo's id if they may see it
        (in the trash too), None if it was purged. Hashes left out are missing for them; the
        id of a photo they can't see is never returned."""
        ...

    def enqueue(self, kind: str, payload: dict[str, object]) -> int: ...


class InboxStore(Protocol):
    def ensure_inbox_source(self, user_id: int, root: str) -> Source:
        """The user's inbox source (kind "inbox"), created on first use; root kept current."""
        ...


@dataclass(frozen=True, slots=True)
class Device:
    id: int
    user_id: int
    name: str
    platform: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class DeviceStore(Protocol):
    def add_device(
        self, user_id: int, name: str, platform: str, token_hash: str, now: datetime
    ) -> Device: ...

    def list_devices(self, user_id: int) -> list[Device]: ...

    def revoke_device(self, user_id: int, device_id: int, now: datetime) -> bool: ...

    def user_for_token_hash(self, token_hash: str, now: datetime) -> int | None:
        """The owner of an active (not revoked) token; records its last use."""
        ...
