"""Edit recipes: store them, and serve thumbnails/previews with the recipe applied.

Rendered edits are cached under ``derived/edited/`` keyed by content hash + recipe key, so
they are made once per recipe and a changed recipe never shows a stale picture.
"""

from datetime import datetime
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.edit_recipe import Recipe
from photo_assistant.domain.library_paths import edited_relpath
from photo_assistant.ports import ImageRenderer, LibraryStore, RenderedImage, RenderSpec
from photo_assistant.ports.library import AssetView


class EditStore(Protocol):
    def get_recipe(self, asset_id: int) -> Recipe | None: ...
    def save_recipe(self, asset_id: int, recipe: Recipe, user_id: int, now: datetime) -> None: ...
    def delete_recipe(self, asset_id: int) -> None: ...
    def set_thumbnail(self, asset_id: int, thumb: RenderedImage) -> None: ...


class Editor:
    def __init__(
        self,
        edits: EditStore,
        store: LibraryStore,
        renderer: ImageRenderer,
        *,
        thumb_edge: int = 640,
        preview_edge: int = 2048,
    ) -> None:
        self._edits = edits
        self._store = store
        self._renderer = renderer
        self._edges = {"thumb": thumb_edge, "preview": preview_edge}

    def recipe_of(self, asset_id: int) -> Recipe:
        return self._edits.get_recipe(asset_id) or Recipe()

    def save(self, asset_id: int, recipe: Recipe, user_id: int, now: datetime) -> Recipe:
        """A recipe that changes nothing is the same as a revert."""
        if recipe.is_identity:
            self.revert(asset_id)
        else:
            self._edits.save_recipe(asset_id, recipe, user_id, now)
        return recipe

    def revert(self, asset_id: int) -> None:
        self._edits.delete_recipe(asset_id)

    def image_for(self, view: AssetView, kind: str) -> Path | None:
        """The WebP to show for ``kind`` (thumb | preview), rendering an edit on first use."""
        a = view.asset
        if view.recipe is None:
            relative = a.thumb_path if kind == "thumb" else (a.preview_path or a.thumb_path)
            if relative is None:
                return None
            path = self._store.absolute(relative)
            if kind == "thumb" and a.thumb_size is None and path.is_file():
                # photos migrated from M1 have no thumbnail size: measure it once (QA A12)
                width, height = self._renderer.dimensions(path)
                self._edits.set_thumbnail(a.id, RenderedImage(relative, width, height))
            return path
        path = self._store.absolute(str(edited_relpath(kind, a.content_hash, view.recipe.key)))
        if not path.is_file():
            spec = RenderSpec(recipe=view.recipe, max_edge=self._edges[kind])
            self._renderer.render_variant(self._store.absolute(a.library_path), path, spec)
        return path
