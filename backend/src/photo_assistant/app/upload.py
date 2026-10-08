"""Uploads from phones and browsers into the uploader's inbox (FEATURES 10.2 to 10.4).

Each user has an inbox source, ``<data>/inbox/<user_id>/``, private to them by default. A file
is received into ``data/tmp`` (hashed on the way), accepted only if its bytes prove it is a
photo and the library doesn't have it yet, then moved atomically into the inbox under a safe,
unique name (``YYYY-MM/<name>``). One import of the inbox is queued per request; a periodic
rescan picks up a file whose request died before that (ARCHITECTURE, "Phone inbox").
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.domain.access import INBOX_KIND, Viewer
from photo_assistant.domain.model import RunStatus, Source
from photo_assistant.domain.uploads import (
    is_content_hash,
    numbered_names,
    safe_upload_name,
    sniff_image_type,
)
from photo_assistant.ports import Clock
from photo_assistant.ports.upload import (
    InboxStore,
    LibraryIndex,
    SpooledUpload,
    SpoolWriter,
    UploadSpool,
)

INBOX_RESCAN_SECONDS = 3600.0  # the safety net; a normal upload queues its own import
NOT_A_PHOTO = "not a photo (only JPEG, PNG, HEIC, WebP, TIFF, GIF, AVIF and RAW are accepted)"


@dataclass(frozen=True, slots=True)
class UploadSettings:
    max_bytes: int = 200 * 1000**2
    min_free_bytes: int = 0  # keep this much of the disk free, as the importer does
    max_check_hashes: int = 5000
    import_job_kind: str = SCAN_JOB_KIND


class UploadOutcome(StrEnum):
    STORED = "stored"  # in the inbox; the queued import will add it to the library
    DUPLICATE = "duplicate"  # the library already has these exact bytes
    REJECTED = "rejected"  # not a photo, too large, too many files


@dataclass(frozen=True, slots=True)
class UploadResult:
    name: str  # as the client sent it
    outcome: UploadOutcome
    stored_as: str | None = None  # relative to the user's inbox folder
    content_hash: str | None = None
    asset_id: int | None = None
    reason: str | None = None


class UploadInbox:
    def __init__(
        self,
        *,
        inbox: InboxStore,
        library: LibraryIndex,
        spool: UploadSpool,
        clock: Clock,
        inbox_root: Path,
        settings: UploadSettings | None = None,
    ) -> None:
        self._inbox = inbox
        self._library = library
        self._spool = spool
        self._clock = clock
        self._root = inbox_root
        self._settings = settings or UploadSettings()

    def start(self) -> SpoolWriter:
        """A writer for the next file; its ``write`` enforces the size limit."""
        return self._spool.open(self._settings.max_bytes)

    def no_room(self, client_name: str) -> UploadResult | None:
        """The refusal for a file arriving while the disk is under its free-space floor
        (asked before a byte of it is stored), or None while there is room."""
        free, floor = self._spool.free_bytes(), self._settings.min_free_bytes
        if free >= floor:
            return None
        reason = (
            f"the library disk is almost full ({free / 1000**3:.1f} GB free; uploads keep at "
            f"least {floor / 1000**3:.0f} GB free): free up space on the server, then send it again"
        )
        return UploadResult(client_name, UploadOutcome.REJECTED, reason=reason)

    def accept(self, viewer: Viewer, client_name: str, spooled: SpooledUpload) -> UploadResult:
        """Store a received photo in the uploader's inbox, unless *they* already have it.

        A photo that exists but is hidden from them is stored like a new one: the inbox import
        then links the existing library photo to their inbox source (one asset, no second
        library file), which is how they gain access to it (QA A7)."""
        digest = spooled.content_hash
        ext = sniff_image_type(spooled.head)
        if ext is None:
            self._spool.discard(spooled)
            return UploadResult(client_name, UploadOutcome.REJECTED, reason=NOT_A_PHOTO)
        present = self._library.hashes_present(viewer, [digest])
        if digest in present:
            self._spool.discard(spooled)
            return UploadResult(
                client_name, UploadOutcome.DUPLICATE, content_hash=digest, asset_id=present[digest]
            )
        user_id = viewer.user_id
        month = self._clock.now().strftime("%Y-%m")
        name = safe_upload_name(client_name, ext)
        folder = self._user_folder(user_id)
        # before the file: an inbox the rescan knows of, even if this request never finishes
        self._inbox.ensure_inbox_source(user_id, str(folder))
        stored = self._spool.commit(spooled, folder / month, numbered_names(name))
        return UploadResult(
            client_name, UploadOutcome.STORED, f"{month}/{stored.name}", content_hash=digest
        )

    def too_large(self, client_name: str) -> UploadResult:
        limit_mb = self._settings.max_bytes / 1000**2
        return UploadResult(
            client_name,
            UploadOutcome.REJECTED,
            reason=f"larger than the {limit_mb:g} MB upload limit",
        )

    def finish_batch(self, user_id: int, results: Sequence[UploadResult]) -> int | None:
        """Queue one import of the inbox if anything new arrived; the job id."""
        if not any(r.outcome is UploadOutcome.STORED for r in results):
            return None
        source = self._inbox.ensure_inbox_source(user_id, str(self._user_folder(user_id)))
        return self._library.enqueue(self._settings.import_job_kind, {"source_id": source.id})

    def rescan(
        self,
        sources: Iterable[Source],
        enqueue_once: Callable[[str, dict[str, object]], int | None],
    ) -> int:
        """Queue an import of every enabled inbox among ``sources`` that has a file waiting,
        unless one is already queued (so they never pile up); how many were queued."""
        queued = 0
        for source in sources:
            if source.kind != INBOX_KIND or not source.enabled or source.owner_id is None:
                continue
            folder = self._user_folder(source.owner_id)
            current = self._inbox.ensure_inbox_source(source.owner_id, str(folder))
            if not self._has_a_file_waiting(current.id, folder):
                continue
            job = enqueue_once(self._settings.import_job_kind, {"source_id": current.id})
            queued += job is not None
        return queued

    def _has_a_file_waiting(self, source_id: int, folder: Path) -> bool:
        """Whether an import of this inbox could find something the last one did not: a file
        that arrived since that import started, or an import that did not finish. Every
        import saves a report, so scanning an unchanged inbox every hour filled the import
        history with "nothing new" rows.

        Limits: a file the last finished import reported as failed is not tried again until
        something else arrives (it is in that report; a rescan by hand retries it); and it
        trusts this machine's clock not to jump back past an import."""
        newest = self._spool.newest_arrival(folder)
        if newest is None:
            return False
        runs = self._library.list_import_runs(source_id, 1)
        if not runs or runs[0]["status"] != RunStatus.DONE:
            return True
        return newest >= datetime.fromisoformat(str(runs[0]["started_at"]))

    def missing(self, viewer: Viewer, hashes: Sequence[str]) -> list[str]:
        """Of these content hashes, the ones this viewer doesn't have (in order, no repeats).
        Purged photos count as present: the phone must not send them again and again."""
        if len(hashes) > self._settings.max_check_hashes:
            raise ValueError(f"send at most {self._settings.max_check_hashes} hashes at a time")
        for value in hashes:
            if not is_content_hash(value):
                raise ValueError(f"not a content hash (64 lowercase hex characters): {value!r}")
        unique = list(dict.fromkeys(hashes))
        present = self._library.hashes_present(viewer, unique)
        return [h for h in unique if h not in present]

    def _user_folder(self, user_id: int) -> Path:
        return self._root / str(int(user_id))
