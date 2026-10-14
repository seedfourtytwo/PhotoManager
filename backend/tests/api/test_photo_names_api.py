"""A photo's display name (FEATURES 4b.7): in its details, and as the name of what downloads."""

import io
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import asset_id_of, import_folder
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

FACEBOOK = "10174880_903634589713690_321783628180766947_n (Copy).jpg"


@pytest.fixture
def ids(admin: TestClient, tmp_path: Path) -> dict[str, int]:
    folder = tmp_path / "photos"
    minute = datetime(2015, 6, 12, 14, 32)
    write_photo(folder / "IMG_4821.JPG", seed=1, taken=minute.replace(second=40))
    write_photo(folder / "IMG_4820.JPG", seed=2, taken=minute.replace(second=5))
    write_photo(folder / "Beach day (Copy).jpg", seed=3)  # no date inside: the file's mtime
    write_photo(folder / FACEBOOK, seed=4)
    source = import_folder(admin, folder, "photos")
    names = ("IMG_4821.JPG", "IMG_4820.JPG", "Beach day (Copy).jpg", FACEBOOK)
    keys = ("second", "first", "beach", "facebook")
    return {k: asset_id_of(admin, source, n) for k, n in zip(keys, names, strict=True)}


def _filename(response: object) -> str:
    """The UTF-8 name from ``filename*``."""
    header: str = response.headers["content-disposition"]  # type: ignore[attr-defined]
    return header.split("filename*=UTF-8''")[1].split(";")[0]


def test_the_details_give_the_display_name_and_keep_the_original_file_name(
    admin: TestClient, ids: dict[str, int]
) -> None:
    first = admin.get(f"/api/assets/{ids['first']}").json()
    assert first["name"] == "2015-06-12 14.32"
    assert first["origins"][0]["relative_path"] == "IMG_4820.JPG", "the original stays readable"
    assert admin.get(f"/api/assets/{ids['second']}").json()["name"] == "2015-06-12 14.32 · 2"
    assert admin.get(f"/api/assets/{ids['beach']}").json()["name"] == "Beach day"
    facebook = ids["facebook"]
    assert admin.get(f"/api/assets/{facebook}").json()["name"] == f"Photo {facebook}"


def test_a_download_is_named_after_the_photo_with_its_real_extension(
    admin: TestClient, ids: dict[str, int]
) -> None:
    second = f"/api/assets/{ids['second']}"
    as_is = admin.get(f"{second}/download")
    assert _filename(as_is) == quote("2015-06-12 14.32 · 2.JPG")
    assert 'filename="2015-06-12 14.32 _ 2.JPG"' in as_is.headers["content-disposition"]
    assert _filename(admin.get(f"{second}/download", params={"format": "webp"})) == quote(
        "2015-06-12 14.32 · 2.webp"
    )
    original = admin.get(f"{second}/original").headers["content-disposition"]
    assert quote("2015-06-12 14.32 · 2.JPG") in original
    beach = admin.get(f"/api/assets/{ids['beach']}/download")
    assert _filename(beach) == quote("Beach day.jpg")


def test_a_zip_names_its_photos_by_default_or_by_their_original_names_when_asked(
    admin: TestClient, ids: dict[str, int]
) -> None:
    body = {"ids": [ids["second"], ids["first"], ids["beach"]]}

    def names(extra: dict[str, str]) -> list[str]:
        response = admin.post("/api/downloads", json=body | extra)
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            return sorted(z.namelist())

    assert names({}) == ["2015-06-12 14.32 · 2.JPG", "2015-06-12 14.32.JPG", "Beach day.jpg"]
    assert names({"naming": "original"}) == [
        "Beach day (Copy).jpg",
        "IMG_4820.JPG",
        "IMG_4821.JPG",
    ]
