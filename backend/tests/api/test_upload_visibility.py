"""Uploads and the "what's new?" check see the library as the uploader does (QA A7).

- a purged photo counts as present: the phone must not upload it again and again;
- a photo the uploader can't see is *missing* for them: uploading it links the existing
  library photo to their inbox (one asset, no second file), so they gain access through
  their own inbox source;
- neither route ever reveals the id of a photo the uploader can't see.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.adapters.filesystem import Blake3Hasher
from tests.api.conftest import add_user, asset_id_of, import_folder, services_of
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


def _upload(client: TestClient, path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        response = client.post("/api/upload", files={"file": (path.name, handle, "image/jpeg")})
    assert response.status_code == 200, response.text
    (result,) = response.json()["files"]
    return result  # type: ignore[no-any-return]


def _missing(client: TestClient, digest: str) -> list[str]:
    response = client.post("/api/upload/check", json={"hashes": [digest]})
    assert response.status_code == 200, response.text
    return response.json()["missing"]  # type: ignore[no-any-return]


def test_a_purged_photo_counts_as_present_for_check_and_upload(
    admin: TestClient, tmp_path: Path
) -> None:
    photo = write_photo(tmp_path / "family" / "gone.jpg", seed=1)
    source = import_folder(admin, tmp_path / "family", "family")
    asset_id = asset_id_of(admin, source, "gone.jpg")
    digest = Blake3Hasher().hash_file(photo)
    assert admin.request("DELETE", "/api/assets", json={"ids": [asset_id]}).is_success
    assert admin.post("/api/trash/empty", json={}).json() == {"purged": 1}

    assert _missing(admin, digest) == [], "purged: the phone must not send it again"
    result = _upload(admin, photo)
    assert result["outcome"] == "duplicate" and result["asset_id"] is None
    inbox = tmp_path / "data" / "inbox"
    assert not list(inbox.rglob("*.jpg")), "nothing stored, no 'gone (2).jpg'"


def test_a_photo_hidden_from_the_uploader_is_linked_to_their_inbox_not_hidden_as_a_duplicate(
    admin: TestClient, tmp_path: Path
) -> None:
    photo = write_photo(tmp_path / "restricted" / "shared.jpg", seed=2)
    source = import_folder(admin, tmp_path / "restricted", "restricted")
    assert admin.put(f"/api/sources/{source}/access", json={"everyone": None, "users": []})
    asset_id = asset_id_of(admin, source, "shared.jpg")
    digest = Blake3Hasher().hash_file(photo)
    lea = add_user(admin, "lea")
    assert lea.get(f"/api/assets/{asset_id}").status_code == 404

    assert _missing(lea, digest) == [digest], "lea can't see it: for her it is missing"
    result = _upload(lea, photo)
    assert result["outcome"] == "stored"
    assert result["asset_id"] is None, "never the id of a photo she can't see"
    services_of(admin).worker.run_until_idle()

    detail = lea.get(f"/api/assets/{asset_id}")
    assert detail.status_code == 200, "linked to her inbox: the same photo, now hers too"
    assert detail.json()["level"] == "edit"
    assert services_of(admin).repo.count_assets() == 1, "no second copy in the library"
    originals = list((tmp_path / "data" / "originals").rglob("*.jpg"))
    assert len(originals) == 1
    assert _missing(lea, digest) == []
    again = _upload(lea, photo)
    assert again["outcome"] == "duplicate" and again["asset_id"] == asset_id
