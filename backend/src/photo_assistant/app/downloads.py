"""Downloads (FEATURES 4b): pick what may be downloaded, name it, produce the bytes.

- Only photos the viewer may *download* are included; the rest are counted as skipped.
- ``original`` without resizing sends the library file untouched. Stripping metadata then
  works on a temporary copy. Anything else renders through libvips with the edit recipe.
- Library files are only ever read. Temporary files live in ``data/tmp`` and are removed as
  soon as they have been sent.
"""

import shutil
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from photo_assistant.app.photo_names import PhotoName
from photo_assistant.domain.access import Level
from photo_assistant.domain.errors import UnavailableError
from photo_assistant.domain.export_naming import (
    ExportOptions,
    estimate_bytes,
    export_extension,
    export_stem,
    folder_for,
    unique_names,
)
from photo_assistant.ports import ImageRenderer, LibraryStore, MetadataStripper, RenderSpec
from photo_assistant.ports.library import AssetView

CHUNK = 1024 * 1024
_KEEPS_FORMAT = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}
MEDIA_TYPES = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class OriginalMissingError(UnavailableError):
    def __init__(self) -> None:
        super().__init__(
            "This photo's original file is missing from the library. Run verify-library to "
            "find what is missing, then put it back from a backup."
        )


@dataclass(frozen=True, slots=True)
class Entry:
    view: AssetView
    name: str  # path inside the ZIP, or the download's file name


def downloadable(views: Sequence[AssetView]) -> list[AssetView]:
    return [v for v in views if v.level >= Level.DOWNLOAD]


def _read(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            yield chunk


class Downloads:
    def __init__(
        self,
        store: LibraryStore,
        renderer: ImageRenderer,
        stripper: MetadataStripper,
        tmp_dir: Path,
    ) -> None:
        self._store = store
        self._renderer = renderer
        self._stripper = stripper
        self._tmp = tmp_dir

    def estimate(self, views: Sequence[AssetView], options: ExportOptions) -> int:
        total = 0
        for v in views:
            a = v.asset
            source = (a.width, a.height) if a.width and a.height else None
            fmt = self.output_format(v, options)
            total += estimate_bytes(a.byte_size, a.mime_type, source, v.display_size, fmt, options)
        return total

    def plan(
        self, views: Sequence[AssetView], names: Mapping[int, PhotoName], options: ExportOptions
    ) -> list[Entry]:
        """``names``: each photo's names (``photo_names``)."""
        paths = []
        for view in views:
            name, taken_at = names[view.id], view.asset.taken_at
            city = view.place.city if view.place else None
            stem = export_stem(name.shown, name.original, taken_at, options.naming, city)
            # the original's own extension (.JPG stays .JPG); the library file's when hidden
            ext = export_extension(
                self.output_format(view, options), name.original or view.asset.library_path
            )
            paths.append(f"{folder_for(taken_at, options.folders)}{stem}{ext}")
        return [Entry(v, n) for v, n in zip(views, unique_names(paths), strict=True)]

    @staticmethod
    def output_format(view: AssetView, options: ExportOptions) -> str:
        """``original`` when the file is sent as it is, else the encoder to use."""
        if options.untouched:
            return "original"
        if options.format != "original":
            return options.format
        return _KEEPS_FORMAT.get(view.asset.mime_type or "", "jpeg")

    def original(self, view: AssetView) -> Path:
        """The photo's library file; OriginalMissingError when it is not on the disk."""
        library_file = self._store.absolute(view.asset.library_path)
        if not library_file.is_file():
            raise OriginalMissingError
        return library_file

    def content(self, view: AssetView, options: ExportOptions) -> Iterator[bytes]:
        """The bytes of one download, produced lazily (nothing happens until iterated, so a
        ZIP lists a failing photo in its manifest; a single download checks ``original``
        first, while it can still answer an error)."""
        library_file = self.original(view)
        fmt = self.output_format(view, options)
        if fmt == "original" and not (options.strip_location or options.strip_all_metadata):
            yield from _read(library_file)
            return
        suffix = export_extension(fmt, library_file.name)
        temp = self._tmp / f"download-{uuid.uuid4().hex}{suffix}"
        self._tmp.mkdir(parents=True, exist_ok=True)
        try:
            self._prepare(view, library_file, temp, fmt, options)
            yield from _read(temp)
        finally:
            temp.unlink(missing_ok=True)

    def _prepare(
        self, view: AssetView, source: Path, temp: Path, fmt: str, options: ExportOptions
    ) -> None:
        if fmt == "original":
            shutil.copyfile(source, temp)  # a copy: the library file is never changed
        else:
            spec = RenderSpec(
                recipe=view.recipe,
                max_edge=options.max_edge,
                format=fmt,
                quality=options.quality,
                keep_metadata=not options.strip_all_metadata,
            )
            self._renderer.render_variant(source, temp, spec)
        if options.strip_all_metadata and fmt == "original":
            self._stripper.strip(temp, location_only=False)
        elif options.strip_location and not options.strip_all_metadata:
            self._stripper.strip(temp, location_only=True)
