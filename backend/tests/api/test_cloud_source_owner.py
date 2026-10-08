"""A cloud source belongs to the admin who adds it, like a folder source (owner decision).

Without an owner, a private mark on its photos hid them from nobody: the rule compares the
marker with the source's owner. One world per provider: the admin adds the source, pulls one
photo and marks it private.
"""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import IntegrationSettings
from tests.api.conftest import BASE, PIN, add_user, make_settings, services_of
from tests.proton_cloud import Cloud
from tests.synthetic import write_photo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed"),
]


@dataclass
class World:
    admin: TestClient
    admin_id: int
    cloud: Cloud
    remote_folder: Path


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    config = tmp_path / "rclone.conf"
    config.write_text("[mega]\ntype = local\n")
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.folder("/", {"type": "folder", "uid": "m", "name": "my-files"})
    settings = make_settings(
        tmp_path / "data",
        integrations=IntegrationSettings(
            rclone_config=config, proton_drive_binary=str(cloud.binary)
        ),
    )
    with TestClient(create_app(settings), base_url=BASE) as admin:
        created = admin.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
        assert created.status_code == 201, created.text
        yield World(admin, created.json()["id"], cloud, tmp_path / "remote")


def _add_source_with_one_photo(world: World, provider: str) -> int:
    """The new source's id; its one photo is pulled and imported."""
    if provider == "rclone":
        write_photo(world.remote_folder / "beach.jpg", seed=1)
        body = {"label": "MEGA", "remote": "mega", "path": str(world.remote_folder)}
        added = world.admin.post("/api/remote-sources", json=body)
    else:
        photo = write_photo(world.remote_folder / "beach.jpg", seed=1)
        world.cloud.state["photos"] = [
            {"uid": "p1", "name": "beach.jpg", "mediaType": "image/jpeg", "source": str(photo)}
        ]
        world.cloud.save()
        added = world.admin.post("/api/proton/sources", json={"label": "P", "path": "/photos"})
    assert added.status_code == 201, added.text
    source_id: int = added.json()["id"]
    assert world.admin.post(f"/api/sources/{source_id}/scan").status_code == 202
    services_of(world.admin).worker.run_until_idle()
    return source_id


def _ids(client: TestClient) -> list[int]:
    return [item["id"] for item in client.get("/api/assets").json()["items"]]


@pytest.mark.parametrize("provider", ["rclone", "proton"])
def test_a_new_cloud_source_belongs_to_the_admin_who_added_it(world: World, provider: str) -> None:
    source_id = _add_source_with_one_photo(world, provider)
    listed = {s["id"]: s for s in world.admin.get("/api/sources").json()}
    assert listed[source_id]["kind"] == provider
    assert listed[source_id]["owner_id"] == world.admin_id


@pytest.mark.parametrize("provider", ["rclone", "proton"])
def test_a_private_photo_from_a_cloud_source_is_hidden_from_other_members(
    world: World, provider: str
) -> None:
    """Exactly as for a folder source: hidden from those who reach it only through the
    marker's own source, still there for the marker (who is the owner here)."""
    _add_source_with_one_photo(world, provider)
    lea = add_user(world.admin, "lea")
    second_admin = add_user(world.admin, "ada", "admin")
    (photo,) = _ids(world.admin)
    assert _ids(lea) == [photo], "open to every member by default, like any source"

    marked = world.admin.patch(f"/api/assets/{photo}/state", json={"private": True})
    assert marked.is_success, marked.text

    assert _ids(lea) == []
    assert lea.get(f"/api/assets/{photo}").status_code == 404
    assert lea.get(f"/api/assets/{photo}/thumb").status_code == 404
    assert _ids(second_admin) == [], "another admin does not see it either"
    assert _ids(world.admin) == [photo]
    assert world.admin.get(f"/api/assets/{photo}").json()["private"] is True


@pytest.mark.parametrize("provider", ["rclone", "proton"])
def test_a_cloud_source_handed_to_a_member_keeps_their_private_photos_theirs(
    world: World, provider: str
) -> None:
    """The marker and the owner can differ from the adding admin: hand the source over."""
    source_id = _add_source_with_one_photo(world, provider)
    lea, tom = add_user(world.admin, "lea"), add_user(world.admin, "tom")
    lea_id = next(u["id"] for u in world.admin.get("/api/users").json() if u["username"] == "lea")
    assert world.admin.patch(f"/api/sources/{source_id}", json={"owner_id": lea_id}).is_success
    (photo,) = _ids(lea)

    assert lea.patch(f"/api/assets/{photo}/state", json={"private": True}).is_success

    assert _ids(lea) == [photo]
    assert _ids(tom) == []
    assert _ids(world.admin) == [], "lea's private photo, reached only through her source"
