"""Background job: render the large preview used by the full-screen viewer.

Runs on a pool of threads of its own (C28). When the photo's thumbnail is missing too (a
repair), both are written from one decode of the original.
"""

from photo_assistant.domain.library_paths import derived_relpath
from photo_assistant.ports import ImageRenderer, LibraryStore, RenderedImage, Repository


class GeneratePreview:
    def __init__(
        self,
        repo: Repository,
        store: LibraryStore,
        renderer: ImageRenderer,
        max_edge: int = 2048,
        thumb_edge: int = 640,
    ) -> None:
        self._repo = repo
        self._store = store
        self._renderer = renderer
        self._max_edge = max_edge
        self._thumb_edge = thumb_edge

    def __call__(self, payload: dict[str, object]) -> None:
        asset_id = int(str(payload["asset_id"]))
        asset = self._repo.get_asset(asset_id)
        if asset is None:
            return  # purged since the job was queued: nothing to render
        original = self._store.absolute(asset.library_path)
        relative = str(derived_relpath("preview", asset.content_hash))
        thumb = asset.thumb_path
        if thumb is None or not self._store.absolute(thumb).is_file():
            thumb = str(derived_relpath("thumb", asset.content_hash))
            size, thumb_size = self._renderer.render_pair(
                original,
                self._store.absolute(relative),
                self._max_edge,
                self._store.absolute(thumb),
                self._thumb_edge,
            )
            self._repo.set_thumbnail(asset_id, RenderedImage(thumb, *thumb_size))
        else:
            size = self._renderer.render(original, self._store.absolute(relative), self._max_edge)
        self._repo.set_preview(asset_id, RenderedImage(relative, *size))
