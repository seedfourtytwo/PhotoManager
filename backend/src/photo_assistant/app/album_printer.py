"""Print an album (FEATURES §6) from the library: photos → print renditions → print engine.

Typst cannot read HEIC or RAW and ignores EXIF orientation, so every photo goes to print as a
*print rendition*: a full-resolution sRGB JPEG with the orientation and the edit recipe applied,
cached per (content, recipe) under ``derived/print/``. Plans and page previews never wait for
them: they use the 2048 px preview with the rendition's pixel size, so the ppi check is the same.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from photo_assistant.app.print_job import (
    InvalidPagesError,
    PrintOptions,
    PrintPhoto,
    PrintPlan,
    PrintResult,
    ResolutionIssue,
    plan_print,
    preview_page,
    print_album,
)
from photo_assistant.domain.edit_recipe import Recipe, edited_size
from photo_assistant.domain.errors import InvalidError
from photo_assistant.domain.library_paths import print_relpath
from photo_assistant.domain.print_layout import Page
from photo_assistant.ports import ImageRenderer, LibraryStore, RenderSpec
from photo_assistant.ports.library import AssetView
from photo_assistant.ports.printing import PrintRenderer

PRINT_QUALITY = 92


@dataclass(frozen=True)
class ManualPage:
    layout_id: str
    asset_ids: tuple[int, ...]
    text: str = ""


@dataclass(frozen=True)
class PrintRequest:
    trim: str = "a4-landscape"
    theme: str = "quiet"
    cover: bool = True
    crop_marks: bool = False
    pages: tuple[ManualPage, ...] | None = None  # None: automatic layout
    allow_low_resolution: bool = False


@dataclass(frozen=True)
class AlbumToPrint:
    title: str
    description: str
    updated_at: datetime  # the PDF's creation date: the same album gives the same bytes
    items: Sequence[AssetView]  # in album order, only what the viewer may print
    cover: AssetView | None


Issue = tuple[int | None, float, str]  # (asset id, ppi, level)


@dataclass(frozen=True)
class AlbumPlan:
    plan: PrintPlan
    pages: tuple[tuple[str, tuple[int, ...], str], ...]  # (layout_id, asset ids, text)
    issues: tuple[Issue, ...]


class AlbumPrintBlockedError(InvalidError):
    """Photos too small to print at this size, by asset id."""

    def __init__(self, issues: tuple[Issue, ...]) -> None:
        super().__init__(f"{len(issues)} photo(s) are too small to print at this size")
        self.issues = issues


def _issues(album: "AlbumToPrint", issues: Sequence[ResolutionIssue]) -> tuple[Issue, ...]:
    cover_id = album.cover.id if album.cover else None
    return tuple(
        (cover_id if i.photo is None else album.items[i.photo].id, i.ppi, i.level.value)
        for i in issues
    )


class PrintRenditions:
    def __init__(
        self,
        store: LibraryStore,
        renderer: ImageRenderer,
        preview_of: Callable[[AssetView], Path | None],
    ) -> None:
        self._store = store
        self._renderer = renderer
        self._preview_of = preview_of  # the (edited) 2048 px preview, if it exists

    def path(self, view: AssetView) -> Path:
        """The cached full-resolution rendition, made on first use."""
        a = view.asset
        recipe = view.recipe or Recipe()
        path = self._store.absolute(str(print_relpath(a.content_hash, recipe.key)))
        if not path.is_file():
            spec = RenderSpec(
                recipe=view.recipe, max_edge=None, format="jpeg", quality=PRINT_QUALITY
            )
            self._renderer.render_variant(self._store.absolute(a.library_path), path, spec)
        return path

    def photo(self, view: AssetView, *, full: bool) -> PrintPhoto:
        """``full``: the rendition itself; else the preview standing in for it (same size)."""
        a = view.asset
        if a.width is None or a.height is None:  # import always records it; be explicit anyway
            raise InvalidPagesError(f"photo {a.id} has no known size and cannot be printed")
        image = self.path(view) if full else (self._preview_of(view) or self.path(view))
        width, height = edited_size(a.width, a.height, view.recipe or Recipe())
        return PrintPhoto(image_path=image, pixel_w=width, pixel_h=height)


class AlbumPrinter:
    def __init__(
        self, renditions: PrintRenditions, renderer_for: Callable[[datetime], PrintRenderer]
    ) -> None:
        self._renditions = renditions
        self._renderer_for = renderer_for

    def _options(
        self, album: AlbumToPrint, req: PrintRequest, *, full: bool
    ) -> tuple[list[PrintPhoto], PrintOptions]:
        photos = [self._renditions.photo(v, full=full) for v in album.items]
        index = {v.id: i for i, v in enumerate(album.items)}
        pages = None
        if req.pages is not None:
            try:
                pages = tuple(
                    Page(p.layout_id, tuple(index[i] for i in p.asset_ids), p.text)
                    for p in req.pages
                )
            except KeyError as exc:
                raise InvalidPagesError(f"photo {exc.args[0]} is not in this album") from exc
        cover = self._renditions.photo(album.cover, full=full) if album.cover else None
        options = PrintOptions(
            title=album.title,
            subtitle=album.description,
            trim=req.trim,
            theme=req.theme,
            cover=req.cover,
            cover_photo=cover if req.cover else None,
            crop_marks=req.crop_marks,
            pages=pages,
            allow_low_resolution=req.allow_low_resolution,
        )
        return photos, options

    def plan(self, album: AlbumToPrint, req: PrintRequest) -> AlbumPlan:
        """Every page decided, without rendering anything (for the page editor)."""
        photos, options = self._options(album, req, full=False)
        plan = plan_print(photos, options)
        by_path = {p.image_path: v.id for p, v in zip(photos, album.items, strict=True)}
        pages = tuple(
            (page.layout_id, tuple(by_path[s.image_path] for s in page.slots), page.text)
            for page in plan.job.pages
        )
        return AlbumPlan(plan, pages, _issues(album, plan.issues))

    def pdf(self, album: AlbumToPrint, req: PrintRequest) -> tuple[PrintResult, tuple[Issue, ...]]:
        """Raises AlbumPrintBlockedError (photos too small) unless low resolution is allowed.
        Checked on the plan first, so a blocked album fails before any rendition is made."""
        planned = self.plan(album, req)
        if planned.plan.blocked and not req.allow_low_resolution:
            raise AlbumPrintBlockedError(planned.issues)
        photos, options = self._options(album, req, full=True)
        # the same photo sizes and options as the plan just checked: it cannot be blocked here
        result = print_album(photos, options, self._renderer_for(album.updated_at))
        return result, _issues(album, result.issues)

    def preview(self, album: AlbumToPrint, req: PrintRequest, page: int, ppi: float) -> bytes:
        photos, options = self._options(album, req, full=False)
        return preview_page(photos, options, self._renderer_for(album.updated_at), page, ppi)
