"""Move the whole library to another machine (laptop → server) and prove it arrived intact.

``export`` writes a consistent database snapshot plus a hash-verified copy of everything that
is not rebuildable. It is resumable: files already at the destination with the same bytes are
skipped, so an interrupted copy of 500 GB just continues. ``verify`` checks that every asset in
a library's database resolves to a file whose BLAKE3 matches (ARCHITECTURE §6), and counts the
originals no asset refers to.

The source library is only ever read.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from photo_assistant.domain.library_paths import (
    DATABASE_FILE,
    LIBRARY_FOLDERS,
    InvalidLibraryPathError,
    ensure_relative,
    nested_or_same,
)
from photo_assistant.ports import Hasher
from photo_assistant.ports.backup import AssetFile
from photo_assistant.ports.library_files import (
    CopyOutcome,
    FileTree,
    LibraryIndex,
    LibraryUnreadableError,
)

DATABASE = DATABASE_FILE
DERIVED_FOLDER = "derived"  # thumbnails and previews: rebuildable, but saves hours of work
IN_PROGRESS_MARKER = ".export-in-progress"
ORIGINALS_FOLDER = "originals"
UNREFERENCED_SAMPLE = 20  # how many leftover originals a report names; the count is exact

Progress = Callable[[str], None]


class LibraryTransferError(RuntimeError):
    """The export can't start or finish; the message says why and what to do."""


@dataclass
class VerifyReport:
    root: Path
    assets_checked: int = 0
    missing: list[str] = field(default_factory=list)
    corrupt: list[str] = field(default_factory=list)
    missing_derived: list[str] = field(default_factory=list)
    # originals on disk that no photo refers to (a purge that stopped half-way): reported,
    # never deleted, and not damage, so they do not make the library "not ok"
    unreferenced: int = 0
    unreferenced_sample: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.corrupt

    def lines(self, show: int = 10) -> list[str]:
        out = [f"  photos checked  {self.assets_checked:>8}"]
        for label, items in (
            ("missing", self.missing),
            ("corrupt", self.corrupt),
            ("no thumbnail", self.missing_derived),
        ):
            out.append(f"  {label:<15} {len(items):>8}")
            out += [f"      {path}" for path in items[:show]]
            if len(items) > show:
                out.append(f"      … and {len(items) - show} more")
        shown = self.unreferenced_sample[:show]
        out.append(f"  {'unreferenced':<15} {self.unreferenced:>8}")
        out += [f"      {path}" for path in shown]
        if self.unreferenced > len(shown):
            out.append(f"      … and {self.unreferenced - len(shown)} more")
        return out


@dataclass
class ExportSummary:
    destination: Path
    copied: int = 0
    already_there: int = 0
    bytes_copied: int = 0
    verify: VerifyReport | None = None

    @property
    def ok(self) -> bool:
        return self.verify is not None and self.verify.ok


def _overlap(a: Path, b: Path) -> bool:
    return nested_or_same(a.resolve(), b.resolve())


class LibraryTransfer:
    def __init__(
        self,
        files: FileTree,
        hasher: Hasher,
        snapshot_database: Callable[[Path, Path], None],
        open_index: Callable[[Path], LibraryIndex],
    ) -> None:
        self._files = files
        self._hasher = hasher
        self._snapshot = snapshot_database
        self._open_index = open_index

    # --- export ----------------------------------------------------------------------------

    def export(
        self,
        source_root: Path,
        destination: Path,
        *,
        include_derived: bool = True,
        progress: Progress | None = None,
    ) -> ExportSummary:
        say = progress or (lambda _message: None)
        self._check_export(source_root, destination)
        destination.mkdir(parents=True, exist_ok=True)
        marker = destination / IN_PROGRESS_MARKER
        marker.touch()
        say("snapshotting the database")
        self._snapshot(source_root / DATABASE, destination / DATABASE)
        summary = ExportSummary(destination)
        folders = [*LIBRARY_FOLDERS, *([DERIVED_FOLDER] if include_derived else [])]
        for folder in folders:
            self._copy_folder(source_root, destination, folder, summary)
            say(f"{folder}: {summary.copied} copied, {summary.already_there} already there")
        say("verifying every photo at the destination")
        summary.verify = self.verify(destination, check_derived=include_derived)
        if summary.verify.ok:
            marker.unlink()
        return summary

    def _check_export(self, source_root: Path, destination: Path) -> None:
        if not (source_root / DATABASE).is_file():
            raise LibraryTransferError(f"no library at {source_root} (no {DATABASE})")
        if _overlap(source_root, destination):
            raise LibraryTransferError("the destination must be outside the library")
        resuming = (destination / IN_PROGRESS_MARKER).exists()
        if (destination / DATABASE).exists() and not resuming:
            raise LibraryTransferError(
                f"{destination} already holds a library; export into an empty folder"
            )

    def _copy_folder(
        self, source_root: Path, destination: Path, folder: str, summary: ExportSummary
    ) -> None:
        for relative in self._files.files_under(source_root, folder):
            result = self._files.copy_verified(source_root / relative, destination / relative)
            if result.outcome is CopyOutcome.COPIED:
                summary.copied += 1
                summary.bytes_copied += result.byte_size
            else:
                summary.already_there += 1

    # --- verify ----------------------------------------------------------------------------

    def verify(self, root: Path, *, check_derived: bool = True) -> VerifyReport:
        if not (root / DATABASE).is_file():
            raise LibraryUnreadableError(f"no library at {root} (no {DATABASE})")
        index = self._open_index(root / DATABASE)
        try:
            return self._verify_all(root, index.assets(), check_derived)
        finally:
            index.close()

    def _verify_all(
        self, root: Path, assets: Iterable[AssetFile], check_derived: bool
    ) -> VerifyReport:
        report = VerifyReport(root)
        referenced = set()
        for asset in assets:
            report.assets_checked += 1
            referenced.add(asset.library_path)
            original = self._inside(root, asset.library_path)
            if original is None or not self._files.is_file(original):
                report.missing.append(asset.library_path)
            elif self._hasher.hash_file(original) != asset.content_hash:
                report.corrupt.append(asset.library_path)
            if check_derived:
                report.missing_derived += self._missing_derived(root, asset)
        for relative in self._files.files_under(root, ORIGINALS_FOLDER):
            if relative not in referenced:
                report.unreferenced += 1
                if len(report.unreferenced_sample) < UNREFERENCED_SAMPLE:
                    report.unreferenced_sample.append(relative)
        return report

    def _missing_derived(self, root: Path, asset: AssetFile) -> list[str]:
        paths = [p for p in (asset.thumb_path, asset.preview_path) if p]
        return [p for p in paths if not self._present(self._inside(root, p))]

    def _present(self, path: Path | None) -> bool:
        return path is not None and self._files.is_file(path)

    @staticmethod
    def _inside(root: Path, relative: str) -> Path | None:
        """A stored path that would escape the data root counts as missing, never followed."""
        try:
            return root / ensure_relative(relative)
        except InvalidLibraryPathError:
            return None
