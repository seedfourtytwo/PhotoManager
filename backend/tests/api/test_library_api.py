"""API tests: the HTTP surface M1 exposes (the web UI builds on these in M2)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.services import Services
from tests.fixtures.expected import DUPLICATE, FAILED, IMPORTED, SKIPPED

pytestmark = pytest.mark.integration


@pytest.fixture
def client(admin: TestClient) -> TestClient:
    return admin


def services(client: TestClient) -> Services:
    s: Services = client.app.state.services  # type: ignore[attr-defined]
    return s


def add_and_scan(client: TestClient, folder: Path) -> dict[str, object]:
    source = client.post("/api/sources", json={"label": "Fixtures", "path": str(folder)}).json()
    response = client.post(f"/api/sources/{source['id']}/scan")
    assert response.status_code == 202
    services(client).worker.run_until_idle()
    return source  # type: ignore[no-any-return]


def test_add_list_and_disable_sources(client: TestClient, source_guard: Path) -> None:
    created = client.post("/api/sources", json={"label": "Pictures", "path": str(source_guard)})
    assert created.status_code == 201
    body = created.json()
    assert body["label"] == "Pictures" and body["enabled"] is True
    assert [s["label"] for s in client.get("/api/sources").json()] == ["Pictures"]
    patched = client.patch(f"/api/sources/{body['id']}", json={"enabled": False})
    assert patched.json()["enabled"] is False


def test_sources_are_validated(client: TestClient, source_guard: Path, tmp_path: Path) -> None:
    missing = client.post("/api/sources", json={"label": "x", "path": str(tmp_path / "nope")})
    assert missing.status_code == 422 and "not a folder" in missing.json()["detail"]
    inside = client.post("/api/sources", json={"label": "x", "path": str(tmp_path / "data")})
    assert inside.status_code == 422 and "library" in inside.json()["detail"]
    parent = client.post("/api/sources", json={"label": "x", "path": str(tmp_path)})
    assert parent.status_code == 422, "a source containing the library would import it into itself"
    client.post("/api/sources", json={"label": "a", "path": str(source_guard)})
    again = client.post("/api/sources", json={"label": "b", "path": str(source_guard)})
    assert again.status_code == 409
    assert client.post("/api/sources/999/scan").status_code == 404
    assert client.patch("/api/sources/999", json={"enabled": False}).status_code == 404


def test_scan_imports_and_report_explains_every_file(
    client: TestClient, source_guard: Path
) -> None:
    source = add_and_scan(client, source_guard)
    runs = client.get("/api/imports", params={"source_id": source["id"]}).json()
    assert len(runs) == 1
    summary = runs[0]["summary"]
    assert summary["imported"] == len(IMPORTED)
    assert summary["duplicate"] == len(DUPLICATE)
    assert summary["skipped"] == len(SKIPPED)
    assert summary["failed"] == len(FAILED)
    report = client.get(f"/api/imports/{runs[0]['id']}", params={"outcome": "failed"}).json()
    assert {i["relative_path"] for i in report["items"]} == FAILED
    assert all(i["reason"] for i in report["items"])
    assert client.get("/api/imports/999").status_code == 404


def test_timeline_pages_through_everything_newest_first(
    client: TestClient, source_guard: Path
) -> None:
    add_and_scan(client, source_guard)
    seen, cursor = [], None
    while True:
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        page = client.get("/api/assets", params=params).json()
        seen += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(IMPORTED)
    dates = [a["taken_at"] for a in seen]
    assert dates == sorted(dates, reverse=True)
    first = seen[0]
    assert set(first) >= {"id", "taken_at", "date_source", "width", "height", "thumb"}
    assert first["thumb"]["url"] == f"/api/assets/{first['id']}/thumb?v=0"
    assert client.get("/api/assets", params={"cursor": "junk"}).status_code == 400


def test_asset_detail_images_and_original_download(client: TestClient, source_guard: Path) -> None:
    add_and_scan(client, source_guard)
    asset = client.get("/api/assets", params={"limit": 100}).json()["items"][0]
    detail = client.get(f"/api/assets/{asset['id']}").json()
    assert detail["origins"] and detail["origins"][0]["source_label"] == "Fixtures"
    thumb = client.get(f"/api/assets/{asset['id']}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"
    assert "immutable" in thumb.headers["cache-control"]
    preview = client.get(f"/api/assets/{asset['id']}/preview")
    assert preview.status_code == 200, "preview jobs ran in add_and_scan"
    original = client.get(f"/api/assets/{asset['id']}/original")
    assert original.status_code == 200
    assert "attachment" in original.headers["content-disposition"]
    assert client.get("/api/assets/999").status_code == 404
    library_file = services(client).store.absolute(
        services(client).repo.get_asset(asset["id"]).library_path  # type: ignore[union-attr]
    )
    library_file.chmod(0o644)
    library_file.unlink()
    missing = client.get(f"/api/assets/{asset['id']}/original")
    assert missing.status_code == 404 and "missing" in missing.json()["detail"]
    assert client.get("/api/assets/999/thumb").status_code == 404


def test_scan_all_queues_only_enabled_sources(
    client: TestClient, source_guard: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    a = client.post("/api/sources", json={"label": "a", "path": str(source_guard)}).json()
    b = client.post("/api/sources", json={"label": "b", "path": str(other)}).json()
    client.patch(f"/api/sources/{b['id']}", json={"enabled": False})
    queued = client.post("/api/sources/scan-all").json()
    assert [q["source_id"] for q in queued] == [a["id"]]


def test_stats_and_jobs(client: TestClient, source_guard: Path) -> None:
    add_and_scan(client, source_guard)
    stats = client.get("/api/stats").json()
    assert stats["assets"] == len(IMPORTED)
    assert stats["sources"] == 1
    assert stats["jobs"]["failed"] == 0
    assert stats["free_bytes"] > 0
    jobs = client.get("/api/jobs", params={"status": "done"}).json()
    assert {j["kind"] for j in jobs} == {"scan_source", "preview"}
    assert client.post("/api/jobs/999/retry").status_code == 404
