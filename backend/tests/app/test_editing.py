"""Editor: cached renders of an edit live exactly as long as its recipe."""

from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.adapters.sqlite_repository import Database, SqliteRepository
from photo_assistant.app.editing import Editor
from photo_assistant.domain.access import Role
from photo_assistant.domain.edit_recipe import Recipe
from photo_assistant.domain.library_paths import edited_relpath
from photo_assistant.ports import RenderSpec
from tests.factories import NOW, new_asset


class WritingRenderer:
    """Writes a marker where a render would go; nothing is decoded."""

    def render_pair(  # type: ignore[no-untyped-def]
        self, source, preview, preview_edge, thumb, thumb_edge, recipe=None
    ):
        for path in (preview, thumb):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"edited")
        return (1, 1), (1, 1)

    def render_variant(self, source: Path, destination: Path, spec: RenderSpec) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"edited")


@pytest.fixture
def world(tmp_path: Path) -> tuple[SqliteRepository, DiskLibraryStore, Editor, int]:
    repo = SqliteRepository(Database.open(":memory:"))
    repo.add_user("c", "C", "hash", Role.ADMIN)
    store = DiskLibraryStore(tmp_path / "data")
    asset_id = repo.add_asset(new_asset(1), NOW)
    return repo, store, Editor(repo, store, WritingRenderer()), asset_id  # type: ignore[arg-type]


def cached(store: DiskLibraryStore) -> list[str]:
    return sorted(p.name for p in store.absolute("derived/edited").rglob("*.webp"))


def renders_of(recipe: Recipe, n: int = 1) -> list[str]:
    return sorted(
        edited_relpath(kind, f"{n:064x}", recipe.key).name for kind in ("preview", "thumb")
    )


def test_saving_another_recipe_removes_the_renders_of_the_one_before(world) -> None:  # type: ignore[no-untyped-def]
    _, store, editor, asset_id = world
    first, second = Recipe(rotate=90), Recipe(rotate=180)
    editor.save(asset_id, first, 1, NOW)
    editor.render_edits({"asset_id": asset_id})
    assert cached(store) == renders_of(first)
    editor.save(asset_id, second, 1, NOW)
    assert cached(store) == [], "the old pair is gone before the new one is rendered"
    editor.render_edits({"asset_id": asset_id})
    assert cached(store) == renders_of(second)


def test_saving_the_same_recipe_again_keeps_its_renders(world) -> None:  # type: ignore[no-untyped-def]
    _, store, editor, asset_id = world
    editor.save(asset_id, Recipe(rotate=90), 1, NOW)
    editor.render_edits({"asset_id": asset_id})
    editor.save(asset_id, Recipe(rotate=90), 1, NOW)
    assert cached(store) == renders_of(Recipe(rotate=90))


@pytest.mark.parametrize("how", ["revert", "save an identity recipe"])
def test_reverting_removes_the_renders_of_the_edit(world, how: str) -> None:  # type: ignore[no-untyped-def]
    repo, store, editor, asset_id = world
    editor.save(asset_id, Recipe(flip_horizontal=True), 1, NOW)
    editor.render_edits({"asset_id": asset_id})
    if how == "revert":
        editor.revert(asset_id)
    else:
        editor.save(asset_id, Recipe(), 1, NOW)
    assert cached(store) == [] and repo.get_recipe(asset_id) is None


def test_another_photos_renders_and_the_original_are_left_alone(world) -> None:  # type: ignore[no-untyped-def]
    repo, store, editor, asset_id = world
    other = repo.add_asset(new_asset(2), NOW)
    original = store.absolute(new_asset(1).library_path)
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    for photo in (asset_id, other):
        editor.save(photo, Recipe(rotate=90), 1, NOW)
        editor.render_edits({"asset_id": photo})
    editor.revert(asset_id)
    assert cached(store) == renders_of(Recipe(rotate=90), n=2)
    assert original.read_bytes() == b"original"


def test_reverting_a_photo_that_was_never_edited_is_fine(world) -> None:  # type: ignore[no-untyped-def]
    _, store, editor, asset_id = world
    editor.revert(asset_id)
    editor.revert(999)
    assert cached(store) == []
