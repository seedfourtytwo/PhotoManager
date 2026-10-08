"""QA A11, the rest: an id beyond SQLite's 64-bit integers is a 422 wherever one is sent in a
query or a body, never a 500 from the database driver."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HUGE = 10**30


@pytest.fixture
def ids(admin: TestClient, tmp_path: Path) -> dict[str, int]:
    folder = tmp_path / "pics"
    folder.mkdir()
    source = admin.post("/api/sources", json={"label": "Pics", "path": str(folder)}).json()
    album = admin.post("/api/albums", json={"title": "Summer"}).json()
    return {"source": source["id"], "album": album["id"]}


def test_ids_beyond_sqlite_integers_are_unprocessable_everywhere(
    admin: TestClient, ids: dict[str, int]
) -> None:
    source, album = ids["source"], ids["album"]
    one_user = [{"user_id": HUGE, "level": "view"}]
    for method, path, body in (
        ("GET", f"/api/imports?source_id={HUGE}", None),
        ("PUT", f"/api/albums/{album}/members", [{"user_id": HUGE, "role": "viewer"}]),
        ("POST", "/api/downloads/estimate", {"album_id": HUGE}),
        ("POST", "/api/people/1/merge", {"source_ids": [HUGE]}),
        ("POST", "/api/people/split", {"face_ids": [HUGE]}),
        ("POST", "/api/people/split", {"face_ids": [1], "person_id": HUGE}),
        ("PATCH", f"/api/sources/{source}", {"owner_id": HUGE}),
        ("PUT", f"/api/sources/{source}/access", {"everyone": None, "users": one_user}),
    ):
        response = admin.request(method, path, json=body)
        assert response.status_code == 422, (method, path, body, response.text)
