"""Background job: render the large preview used by the full-screen viewer."""

from photo_assistant.domain.library_paths import derived_relpath
from photo_assistant.ports import ImageRenderer, LibraryStore, RenderedImage, Repository


class GeneratePreview:
    def __init__(
        self,
        repo: Repository,
        store: LibraryStore,
        renderer: ImageRenderer,
        max_edge: int = 2048,
    ) -> None:
        self._repo = repo
        self._store = store
        self._renderer = renderer
        self._max_edge = max_edge

    def __call__(self, payload: dict[str, object]) -> None:
        asset_id = int(str(payload["asset_id"]))
        asset = self._repo.get_asset(asset_id)
        if asset is None:
            raise LookupError(f"no asset {asset_id}")
        relative = str(derived_relpath("preview", asset.content_hash))
        size = self._renderer.render(
            self._store.absolute(asset.library_path), self._store.absolute(relative), self._max_edge
        )
        self._repo.set_preview(asset_id, RenderedImage(relative, *size))
