"""Edit recipes over HTTP: stored per photo, applied to thumbnails/previews, never to originals."""

import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.api.conftest import add_user, asset_id_of, import_folder, services_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


@pytest.fixture
def photo(admin: TestClient, tmp_path: Path) -> int:
    write_photo(tmp_path / "src" / "wide.jpg", seed=3, size=(300, 200))
    source = import_folder(admin, tmp_path / "src", "src")
    return asset_id_of(admin, source, "wide.jpg")


def image_size(response_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(response_bytes)) as im:
        return im.size


def test_recipe_round_trip_changes_thumb_and_version(admin: TestClient, photo: int) -> None:
    identity = {
        "rotate": 0,
        "flip_horizontal": False,
        "flip_vertical": False,
        "crop": None,
        "straighten": 0.0,
    }
    assert admin.get(f"/api/assets/{photo}/edit").json() == identity
    before = admin.get(f"/api/assets/{photo}").json()
    assert before["edited"] is False and before["thumb"]["url"].endswith("?v=0")
    library = services_of(admin).store.absolute(
        services_of(admin).repo.get_asset(photo).library_path  # type: ignore[union-attr]
    )
    original_hash = hashlib.sha256(library.read_bytes()).hexdigest()

    recipe = identity | {"rotate": 90, "crop": {"x": 0, "y": 0, "w": 1, "h": 0.5}}
    saved = admin.put(f"/api/assets/{photo}/edit", json=recipe)
    assert saved.status_code == 200 and saved.json()["rotate"] == 90
    after = admin.get(f"/api/assets/{photo}").json()
    assert after["edited"] is True
    assert (after["width"], after["height"]) == (200, 150)
    assert after["thumb"]["url"].endswith("?v=1")
    thumb = admin.get(after["thumb"]["url"])
    assert thumb.status_code == 200 and image_size(thumb.content) == (200, 150)
    preview = admin.get(f"/api/assets/{photo}/preview")
    assert image_size(preview.content) == (200, 150)
    edited_dir = services_of(admin).store.absolute("derived/edited")
    assert len(list(edited_dir.rglob("*.webp"))) == 2, "renders are cached"

    assert admin.delete(f"/api/assets/{photo}/edit").status_code == 204
    reverted = admin.get(f"/api/assets/{photo}").json()
    assert reverted["edited"] is False and reverted["thumb"]["url"].endswith("?v=2")
    assert image_size(admin.get(f"/api/assets/{photo}/thumb").content) == (300, 200)
    assert hashlib.sha256(library.read_bytes()).hexdigest() == original_hash, "original untouched"


def test_invalid_recipes_are_refused(admin: TestClient, photo: int) -> None:
    bad = admin.put(f"/api/assets/{photo}/edit", json={"rotate": 45})
    assert bad.status_code == 422
    crop = admin.put(
        f"/api/assets/{photo}/edit", json={"crop": {"x": 0.8, "y": 0, "w": 0.5, "h": 0.5}}
    )
    assert crop.status_code == 422 and "inside" in crop.json()["detail"]
    tiny = {"crop": {"x": 0, "y": 0, "w": 1e-12, "h": 0.5}}
    assert admin.put(f"/api/assets/{photo}/edit", json=tiny).status_code == 422


def test_editing_needs_edit_access(admin: TestClient, photo: int) -> None:
    lea = add_user(admin, "lea")  # everyone has download on new sources
    assert lea.get(f"/api/assets/{photo}/edit").status_code == 200
    assert lea.put(f"/api/assets/{photo}/edit", json={"rotate": 90}).status_code == 403
    assert lea.delete(f"/api/assets/{photo}/edit").status_code == 403
    assert admin.get("/api/assets/999/edit").status_code == 404


def test_saving_a_recipe_queues_both_edited_renders(admin: TestClient, photo: int) -> None:
    """C31: the edited thumbnail and preview are rendered in the background, from one decode,
    instead of on the first (slow) request."""
    from tests.api.conftest import services_of

    services = services_of(admin)
    assert admin.put(f"/api/assets/{photo}/edit", json={"rotate": 90}).is_success
    queued = [j for j in services.repo.list_jobs("queued") if j["kind"] == "render_edit"]
    assert [j["payload"] for j in queued] == [{"asset_id": photo}]
    services.worker.run_until_idle()
    edited = sorted(
        p.name.rsplit("-", 1)[-1] for p in services.store.absolute("derived/edited").rglob("*.webp")
    )
    assert edited == ["preview.webp", "thumb.webp"]
    assert admin.put(f"/api/assets/{photo}/edit", json={}).is_success  # a revert
    assert not [j for j in services.repo.list_jobs("queued") if j["kind"] == "render_edit"]
