"""A photo's detail says how it was exposed (docs/contracts/api-v1.md, v1.6)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.domain.exposure import Exposure
from tests.api.conftest import asset_id_of, import_folder
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

FIELDS = ("f_number", "exposure_time", "iso", "focal_length")


@pytest.fixture
def folder(admin: TestClient, tmp_path: Path) -> int:
    pics = tmp_path / "pics"
    full = Exposure(f_number=2.8, exposure_time=1 / 250, iso=400, focal_length=35.0)
    write_photo(pics / "full.jpg", seed=1, exposure=full)
    write_photo(pics / "some.jpg", seed=2, exposure=Exposure(iso=800, focal_length=4.25))
    write_photo(pics / "scan.jpg", seed=3)
    return import_folder(admin, pics, "Pics")


def exposure_of(admin: TestClient, source: int, name: str) -> dict[str, object]:
    detail = admin.get(f"/api/assets/{asset_id_of(admin, source, name)}").json()
    assert set(FIELDS) <= set(detail), "all four are always there, null when unknown"
    return {field: detail[field] for field in FIELDS}


def test_detail_gives_aperture_shutter_seconds_iso_and_focal_length(
    admin: TestClient, folder: int
) -> None:
    assert exposure_of(admin, folder, "full.jpg") == {
        "f_number": 2.8,
        "exposure_time": 0.004,
        "iso": 400,
        "focal_length": 35.0,
    }


def test_detail_gives_null_for_each_value_the_photo_does_not_carry(
    admin: TestClient, folder: int
) -> None:
    assert exposure_of(admin, folder, "some.jpg") == {
        "f_number": None,
        "exposure_time": None,
        "iso": 800,
        "focal_length": 4.25,
    }
    assert exposure_of(admin, folder, "scan.jpg") == dict.fromkeys(FIELDS)


def test_the_timeline_rows_do_not_carry_exposure(admin: TestClient, folder: int) -> None:
    """Only the detail of one photo does: the grid's pages stay as small as they were."""
    rows = admin.get("/api/assets", params={"limit": 10}).json()["items"]
    assert len(rows) == 3 and all(not set(FIELDS) & set(row) for row in rows)
