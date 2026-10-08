"""Browsing the server's folders to pick one (issue 7): admin only, read-only."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import add_user, services_of


@pytest.fixture
def home(admin: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The test's folder as the home folder: the app's data lives in ``tmp_path / data``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Pictures" / "2019").mkdir(parents=True)
    (tmp_path / "Documents").mkdir()
    return tmp_path


def test_without_a_path_the_home_folder_is_listed_minus_the_library(
    admin: TestClient, home: Path
) -> None:
    listed = admin.get("/api/folders")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["path"] == str(home) and body["parent"] == str(home.parent)
    names = [f["name"] for f in body["folders"]]
    assert names == ["Documents", "Pictures"]
    assert "data" not in names, "the library's own folder is never offered"
    assert body["roots"][0] == {"label": "Home", "path": str(home)}
    assert body["source_problem"] == "this folder contains the photo library itself"


def test_a_plain_photo_folder_can_be_added_and_then_says_it_already_is(
    admin: TestClient, home: Path
) -> None:
    pictures = home / "Pictures"
    first = admin.get("/api/folders", params={"path": str(pictures)}).json()
    assert [f["name"] for f in first["folders"]] == ["2019"] and first["source_problem"] is None
    admin.post("/api/sources", json={"label": "Old disk", "path": str(pictures)})
    again = admin.get("/api/folders", params={"path": str(pictures)}).json()
    assert again["source_problem"] == "already added as “Old disk”"


def test_the_library_folder_and_everything_inside_it_cannot_be_opened(
    admin: TestClient, home: Path
) -> None:
    root = services_of(admin).store.root
    for inside in (root, root / "originals"):
        refused = admin.get("/api/folders", params={"path": str(inside)})
        assert refused.status_code == 422 and "photo library itself" in refused.json()["detail"]


@pytest.mark.parametrize(
    ("path", "word"),
    [
        ("Pictures", "full path"),
        ("/home/c/bad\nname", "control character"),
        ("/home/c/tab\there", "control character"),
        ("/" + "x" * 5000, "too long"),
        ("/definitely/not/here", "not found"),
    ],
)
def test_bad_paths_are_refused_with_the_reason(
    admin: TestClient, home: Path, path: str, word: str
) -> None:
    refused = admin.get("/api/folders", params={"path": path})
    assert refused.status_code == 422 and word in refused.json()["detail"]


def test_a_folder_holding_a_backup_cannot_become_a_source(admin: TestClient, home: Path) -> None:
    disk = home / "usb"
    disk.mkdir()
    made = admin.post("/api/backups/setup", json={"label": "USB", "place": str(disk)})
    assert made.status_code == 201, made.text
    body = admin.get("/api/folders", params={"path": str(disk)}).json()
    assert body["source_problem"] == "this folder holds a backup"


def test_only_admins_browse_the_servers_folders(admin: TestClient, home: Path) -> None:
    assert add_user(admin, "lea").get("/api/folders").status_code == 403
    assert add_user(admin, "gus", "guest").get("/api/folders").status_code == 403


def test_adding_a_source_refuses_control_characters_in_the_path(
    admin: TestClient, home: Path
) -> None:
    refused = admin.post("/api/sources", json={"label": "x", "path": f"{home}/Pic\ntures"})
    assert refused.status_code == 422 and "control character" in refused.json()["detail"]
