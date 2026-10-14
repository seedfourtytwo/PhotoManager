"""ImportSource: bring every photo from one source folder into the library.

Guarantees (tested in tests/app/test_import_source.py):
- the source is only ever read; originals are copied, verified by hash, never moved;
- idempotent: running twice imports nothing new and writes no files;
- every file seen ends in exactly one outcome, and every skip or failure says why;
- the same photo found in several places or sources becomes one asset with many origins.
"""

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path, PurePosixPath

from photo_assistant.app.enrich import FULL_REGROUP, GROUP_JOB
from photo_assistant.app.trash import TRASH_DAYS
from photo_assistant.domain.capture_time import pick_capture_time
from photo_assistant.domain.errors import UnavailableError
from photo_assistant.domain.library_paths import derived_relpath, original_relpath
from photo_assistant.domain.media_types import (
    MediaKind,
    classify,
    edited_original_name,
    edited_original_stem,
    is_picture,
)
from photo_assistant.domain.model import (
    ImportReport,
    ItemResult,
    NewAsset,
    Outcome,
    PhotoMetadata,
    RunStatus,
    Source,
)
from photo_assistant.ports import (
    Clock,
    DuplicateAssetError,
    Hasher,
    ImageRenderer,
    LibraryStore,
    MetadataReader,
    RenderedImage,
    Repository,
    SourceFile,
    SourceReader,
)

log = logging.getLogger(__name__)

PREVIEW_JOB = "preview"
PURGED_REASON = "deleted from the library earlier"
PAUSED_REASON = "not processed: import paused because free disk space is low"
# A file whose content changed since its last import: what became of the photo it held before.
CHANGED_KEPT = "file changed since the last import; previous version kept"
CHANGED_TRASHED = f"{CHANGED_KEPT} in the trash for {TRASH_DAYS} days"


class SourceUnavailableError(UnavailableError):
    """The source can't be imported right now (missing, unplugged, disabled)."""


@dataclass(frozen=True, slots=True)
class ImportSettings:
    min_free_bytes: int = 10 * 1000**3  # FEATURES 11.4: stop before the disk fills up
    thumb_edge: int = 640
    metadata_batch: int = 50
    # Where a timestamp in a file name (FB_IMG_<milliseconds>) becomes local time, with the
    # zone's offset on the photo's own day. None = this machine's zone.
    local_tz: tzinfo | None = None


@dataclass(frozen=True, slots=True)
class _Candidate:
    file: SourceFile
    kind: MediaKind
    content_hash: str


@dataclass(frozen=True, slots=True)
class _Deferred:
    """A file whose content matches another *new* file in the same run."""

    file: SourceFile
    content_hash: str
    first_path: str


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
NOT_UTF8_REASON = (
    "file name is not valid UTF-8 (often from an old Windows or USB disk); rename the file"
)
CONTROL_REASON = "file name contains a line break or other control character; rename the file"


def printable_name(name: str) -> str:
    """A version of a file name that is always valid, printable text (for reports/DB)."""
    return name.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def _name_problem(name: str) -> str | None:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return NOT_UTF8_REASON
    return CONTROL_REASON if _CONTROL.search(name) else None


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return text[-1].strip() if text else type(exc).__name__


def _photo_stems(files: Iterable[SourceFile]) -> set[tuple[str, str]]:
    return {_stem_key(f.relative_path) for f in files if is_picture(f.relative_path)}


def _stem_key(relative_path: str) -> tuple[str, str]:
    """(folder, name without extension, lower case): what a photo shares with its Live Photo
    video and with its edit."""
    path = PurePosixPath(relative_path)
    return str(path.parent), path.stem.lower()


def _pictures_by_stem(items: Iterable[ItemResult]) -> dict[tuple[str, str], int]:
    """The asset behind each (folder, stem); the first path in name order when several
    extensions share one."""
    found: dict[tuple[str, str], int] = {}
    for item in sorted(items, key=lambda i: i.relative_path):
        if item.asset_id is not None and is_picture(item.relative_path):
            found.setdefault(_stem_key(item.relative_path), item.asset_id)
    return found


class ImportSource:
    def __init__(
        self,
        *,
        repo: Repository,
        reader: SourceReader,
        hasher: Hasher,
        metadata: MetadataReader,
        renderer: ImageRenderer,
        store: LibraryStore,
        clock: Clock,
        settings: ImportSettings | None = None,
    ) -> None:
        self._repo = repo
        self._reader = reader
        self._hasher = hasher
        self._metadata = metadata
        self._renderer = renderer
        self._store = store
        self._clock = clock
        self._settings = settings or ImportSettings()

    # --- public ----------------------------------------------------------------------------

    def run(self, source_id: int) -> tuple[int, ImportReport]:
        """Import one source. Raises SourceUnavailableError or ImportBusyError up front;
        any other failure still saves a report (status "failed") before re-raising."""
        source = self._require_source(source_id)
        with self._store.exclusive_import():
            started = self._clock.now()
            try:
                files = self._list_files(source)
            except SourceUnavailableError as exc:
                # put it where the user looks: the source's import history (QA A13)
                failed = ImportReport(source.id, RunStatus.FAILED, message=str(exc))
                self._repo.save_import_report(failed, started, self._clock.now())
                raise
            log.info("import started", extra={"source_id": source.id, "files": len(files)})
            report = ImportReport(source_id=source.id)
            try:
                self._run_steps(source, files, report)
            except Exception as exc:
                report.status = RunStatus.FAILED
                report.message = f"import stopped by an unexpected error: {_first_line(exc)}"
                self._repo.save_import_report(report, started, self._clock.now())
                log.exception("import failed", extra={"source_id": source.id})
                raise
            run_id = self._repo.save_import_report(report, started, self._clock.now())
        log.info("import finished", extra={"source_id": source.id, **report.summary()})
        return run_id, report

    def _run_steps(self, source: Source, files: list[SourceFile], report: ImportReport) -> None:
        new, deferred = self._triage(source, files, report)
        self._import_new(source, new, report)
        self._resolve_deferred(source, deferred, report)
        self._link_edits(source, report)
        if report.status is RunStatus.RUNNING:
            report.status = RunStatus.DONE

    # --- steps -----------------------------------------------------------------------------

    def _require_source(self, source_id: int) -> Source:
        source = self._repo.get_source(source_id)
        if source is None:
            raise SourceUnavailableError(f"no source with id {source_id}")
        if not source.enabled:
            raise SourceUnavailableError(f"source '{source.label}' is disabled")
        if self._store.overlaps(Path(source.root)):
            raise SourceUnavailableError(
                f"source '{source.label}' contains the photo library itself; "
                "point it at a folder outside the library"
            )
        return source

    def _list_files(self, source: Source) -> list[SourceFile]:
        try:
            return list(self._reader.walk(source))
        except OSError as exc:
            if isinstance(exc, FileNotFoundError) and not Path(source.root).is_dir():
                raise SourceUnavailableError(
                    f"source '{source.label}' folder not found: {source.root}"
                ) from exc
            raise SourceUnavailableError(
                f"source '{source.label}' could not be read: {exc.strerror or exc}"
            ) from exc

    def _triage(
        self, source: Source, files: list[SourceFile], report: ImportReport
    ) -> tuple[list[_Candidate], list[_Deferred]]:
        """Sort files into: reported now, or new content to import, or same-as-a-new-file."""
        stems = _photo_stems(files)
        new: list[_Candidate] = []
        deferred: list[_Deferred] = []
        first_seen: dict[str, str] = {}
        for f in files:
            kind = classify(f.relative_path)
            early = self._early_outcome(f, kind, stems)
            if early == "ignored":
                report.ignored += 1
                continue
            if isinstance(early, ItemResult):
                report.add(early)
                continue
            unchanged = self._unchanged(source, f)
            if unchanged is not None:
                report.add(unchanged)
                continue
            try:
                digest = self._hasher.hash_file(f.absolute_path)
            except OSError as exc:
                report.add(ItemResult(f.relative_path, Outcome.FAILED, f"cannot read: {exc}"))
                continue
            known = self._purged_outcome(f, digest) or self._known_outcome(source, f, digest)
            if known is not None:
                report.add(known)
            elif digest in first_seen:
                deferred.append(_Deferred(f, digest, first_seen[digest]))
            else:
                first_seen[digest] = f.relative_path
                new.append(_Candidate(f, kind, digest))
        return new, deferred

    @staticmethod
    def _early_outcome(
        f: SourceFile, kind: MediaKind, photo_stems: set[tuple[str, str]]
    ) -> ItemResult | str | None:
        path = PurePosixPath(f.relative_path)
        if kind is MediaKind.IGNORED:
            return "ignored"
        problem = _name_problem(f.relative_path)
        if problem is not None:
            return ItemResult(printable_name(f.relative_path), Outcome.FAILED, problem)
        if kind is MediaKind.VIDEO:
            is_live = _stem_key(f.relative_path) in photo_stems
            reason = "Live Photo video half" if is_live else "video"
            return ItemResult(
                f.relative_path, Outcome.SKIPPED, f"{reason} (videos not supported yet)"
            )
        if kind is MediaKind.UNSUPPORTED:
            ext = path.suffix.lower().lstrip(".") or "no extension"
            return ItemResult(f.relative_path, Outcome.SKIPPED, f"not a photo ({ext})")
        if f.byte_size == 0:
            return ItemResult(f.relative_path, Outcome.FAILED, "empty file (0 bytes)")
        return None

    def _unchanged(self, source: Source, f: SourceFile) -> ItemResult | None:
        """Same path, size and modification time as last import: skip hashing."""
        known = self._repo.fingerprint_of(source.id, f.relative_path)
        if known is None or known[1] != f.fingerprint:
            return None
        asset = self._repo.get_asset(known[0])
        if asset is None or asset.thumb_path is None:
            return None  # let the slow path repair it
        return ItemResult(f.relative_path, Outcome.ALREADY_KNOWN, asset_id=asset.id)

    def _purged_outcome(self, f: SourceFile, digest: str) -> ItemResult | None:
        """FEATURES 11.3: a photo purged from the library stays out, even if a source
        still has it."""
        if self._repo.is_purged_hash(digest):
            return ItemResult(f.relative_path, Outcome.SKIPPED, PURGED_REASON)
        return None

    def _known_outcome(self, source: Source, f: SourceFile, digest: str) -> ItemResult | None:
        asset_id = self._repo.find_asset_id_by_hash(digest)
        if asset_id is None:
            return None
        self._repair_if_needed(asset_id, f)
        before = self._repo.asset_id_for_source_path(source.id, f.relative_path)
        earlier = self._repo.previous_path_in_source(asset_id, source.id, exclude=f.relative_path)
        changed = self._link(asset_id, source, f, before)
        if before == asset_id:
            return ItemResult(f.relative_path, Outcome.ALREADY_KNOWN, asset_id=asset_id)
        reason = (
            f"same photo as {earlier} (renamed, moved or copied)"
            if earlier
            else "same photo already in the library"
        )
        if changed:
            reason = f"{reason}; {changed}"
        return ItemResult(f.relative_path, Outcome.DUPLICATE, reason, asset_id)

    def _link(self, asset_id: int, source: Source, f: SourceFile, before: int | None) -> str | None:
        """Record that the file at this path holds ``asset_id``. ``before``: the photo the
        path held until now. Returns what to tell about that one, if the file changed."""
        self._repo.add_asset_source(asset_id, source.id, f.relative_path, f.fingerprint)
        if self._repo.restore_superseded(asset_id):  # a file holds it again
            self._repo.enqueue_once(GROUP_JOB, FULL_REGROUP)
        return self._superseded(before, asset_id)

    def _superseded(self, before: int | None, now_holds: int) -> str | None:
        """The path held photo ``before`` and its file now holds another one. A photo is
        seen through its sources, so one that no file holds any more would be gone from
        every member's view and stay in the library unseen: it goes to the trash instead,
        where it can be restored for TRASH_DAYS."""
        if before is None or before == now_holds:
            return None
        if not self._repo.trash_superseded(before, self._clock.now()):
            return CHANGED_KEPT  # another file still holds it
        self._repo.enqueue_once(GROUP_JOB, FULL_REGROUP)  # groups lose a member
        log.info("superseded photo moved to the trash", extra={"asset_id": before})
        return CHANGED_TRASHED

    def _repair_if_needed(self, asset_id: int, f: SourceFile) -> None:
        """A photo recorded without its thumbnail (e.g. by an older version or a crash) gets
        one now, plus its preview job."""
        asset = self._repo.get_asset(asset_id)
        if asset is None or asset.thumb_path is not None:
            return
        thumb_path = str(derived_relpath("thumb", asset.content_hash))
        try:
            size = self._renderer.render(
                f.absolute_path, self._store.absolute(thumb_path), self._settings.thumb_edge
            )
        except Exception:
            log.warning("thumbnail repair failed", extra={"asset_id": asset_id}, exc_info=True)
            return
        self._repo.set_thumbnail(asset_id, RenderedImage(thumb_path, *size))
        self._repo.enqueue(PREVIEW_JOB, {"asset_id": asset_id})
        log.info("repaired missing thumbnail", extra={"asset_id": asset_id})

    def _import_new(self, source: Source, new: list[_Candidate], report: ImportReport) -> None:
        batch_size = self._settings.metadata_batch
        for start in range(0, len(new), batch_size):
            batch = new[start : start + batch_size]
            metas = self._metadata.read_many([c.file.absolute_path for c in batch])
            for index, (candidate, meta) in enumerate(zip(batch, metas, strict=True)):
                if not self._enough_disk(candidate.file.byte_size):
                    self._pause(report, new[start + index :])
                    return
                report.add(self._import_one(source, candidate, meta))

    def _enough_disk(self, incoming: int) -> bool:
        return self._store.free_bytes() - incoming >= self._settings.min_free_bytes

    def _pause(self, report: ImportReport, remaining: Sequence[_Candidate]) -> None:
        free_gb = self._store.free_bytes() / 1000**3
        need_gb = self._settings.min_free_bytes / 1000**3
        report.status = RunStatus.PAUSED_LOW_DISK
        report.message = (
            f"Paused: only {free_gb:.1f} GB free on the library disk; "
            f"import keeps at least {need_gb:.0f} GB free. Free up space and run it again."
        )
        for candidate in remaining:
            report.add(ItemResult(candidate.file.relative_path, Outcome.SKIPPED, PAUSED_REASON))

    def _import_one(self, source: Source, c: _Candidate, meta: PhotoMetadata) -> ItemResult:
        path = c.file.relative_path
        if meta.error:
            return ItemResult(path, Outcome.FAILED, meta.error)
        new_asset = self._describe(c, meta)
        thumb_path = str(derived_relpath("thumb", c.content_hash))
        try:
            thumb_size = self._renderer.render(
                c.file.absolute_path, self._store.absolute(thumb_path), self._settings.thumb_edge
            )
        except Exception as exc:
            return ItemResult(path, Outcome.FAILED, f"cannot decode image: {_first_line(exc)}")
        try:
            self._store.store_original(c.file.absolute_path, new_asset.library_path, c.content_hash)
        except (OSError, RuntimeError) as exc:
            self._store.absolute(thumb_path).unlink(missing_ok=True)
            return ItemResult(path, Outcome.FAILED, f"copy into library failed: {exc}")
        thumb = RenderedImage(thumb_path, *thumb_size)
        replaced = self._repo.asset_id_for_source_path(source.id, path)
        try:
            asset_id = self._repo.record_import(
                new_asset,
                self._clock.now(),
                source.id,
                path,
                thumb,
                PREVIEW_JOB,
                c.file.fingerprint,
            )
        except DuplicateAssetError as dup:  # imported concurrently from elsewhere
            changed = self._link(dup.asset_id, source, c.file, replaced)
            reason = "same photo already in the library"
            if changed:
                reason = f"{reason}; {changed}"
            return ItemResult(path, Outcome.DUPLICATE, reason, dup.asset_id)
        return ItemResult(path, Outcome.IMPORTED, self._superseded(replaced, asset_id), asset_id)

    def _describe(self, c: _Candidate, meta: PhotoMetadata) -> NewAsset:
        name = PurePosixPath(c.file.relative_path)
        taken = pick_capture_time(
            meta.dates,
            filename=name.name,
            file_mtime=c.file.mtime,
            now=self._clock.now(),
            to_local=lambda moment: moment.astimezone(self._settings.local_tz),
        )
        width, height = meta.display_size or (None, None)
        return NewAsset(
            content_hash=c.content_hash,
            kind=c.kind,
            mime_type=meta.mime_type,
            byte_size=c.file.byte_size,
            width=width,
            height=height,
            taken_at=taken.value,
            tz_offset_minutes=taken.tz_offset_minutes,
            date_source=taken.source,
            latitude=meta.latitude,
            longitude=meta.longitude,
            camera_make=meta.camera_make,
            camera_model=meta.camera_model,
            orientation=meta.orientation,
            library_path=str(
                original_relpath(c.content_hash, taken.value.year, taken.value.month, name.suffix)
            ),
            exposure=meta.exposure,
        )

    def _resolve_deferred(
        self, source: Source, deferred: list[_Deferred], report: ImportReport
    ) -> None:
        paused = report.status is RunStatus.PAUSED_LOW_DISK
        for d in deferred:
            asset_id = self._repo.find_asset_id_by_hash(d.content_hash)
            if asset_id is not None:
                before = self._repo.asset_id_for_source_path(source.id, d.file.relative_path)
                changed = self._link(asset_id, source, d.file, before)
                reason = f"same photo as {d.first_path}"
                if changed:
                    reason = f"{reason}; {changed}"
                report.add(ItemResult(d.file.relative_path, Outcome.DUPLICATE, reason, asset_id))
            elif paused:
                report.add(ItemResult(d.file.relative_path, Outcome.SKIPPED, PAUSED_REASON))
            else:
                reason = f"same content as {d.first_path}, which failed"
                report.add(ItemResult(d.file.relative_path, Outcome.FAILED, reason))

    def _link_edits(self, source: Source, report: ImportReport) -> None:
        """FEATURES 11.8: an iPhone ``IMG_E1234`` edit points at ``IMG_1234``: the file with
        the edit's own extension if there is one, else any photo of that name beside it."""
        known = {
            i.relative_path.lower(): i.asset_id for i in report.items if i.asset_id is not None
        }
        by_stem = _pictures_by_stem(report.items)
        for item in report.items:
            if item.outcome is not Outcome.IMPORTED or item.asset_id is None:
                continue
            path = PurePosixPath(item.relative_path)
            original_name = edited_original_name(path.name)
            original_stem = edited_original_stem(path.name)
            if original_name is None or original_stem is None:
                continue
            original_path = str(path.parent / original_name)
            original_id = (
                known.get(original_path.lower())
                or self._repo.asset_id_for_source_path(source.id, original_path)
                or by_stem.get((str(path.parent), original_stem.lower()))
            )
            if original_id is not None and original_id != item.asset_id:
                self._repo.set_variant_of(item.asset_id, original_id)
