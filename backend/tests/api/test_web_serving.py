from pathlib import Path

from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import Settings


def test_built_web_app_is_served_with_client_side_routing(tmp_path: Path) -> None:
    web = tmp_path / "web"
    (web / "_app").mkdir(parents=True)
    (web / "index.html").write_text("<html>app shell</html>")
    (web / "_app" / "main.js").write_text("console.log(1)")
    settings = Settings(data_root=tmp_path / "data", worker_enabled=False, web_dir=web)
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert "app shell" in client.get("/").text
        assert client.get("/_app/main.js").text == "console.log(1)"
        assert "app shell" in client.get("/albums/42").text, "deep links load the app"
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/nope").status_code == 404, "API 404s stay 404s"


def test_without_a_build_only_the_api_is_served(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "data", worker_enabled=False, web_dir=tmp_path / "x")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200


def test_hashed_build_files_are_cached_forever_and_the_shell_is_not(tmp_path: Path) -> None:
    """C30: /_app/immutable/* names change with their content."""
    web = tmp_path / "web"
    (web / "_app" / "immutable").mkdir(parents=True)
    (web / "index.html").write_text("<html>app shell</html>")
    (web / "_app" / "immutable" / "start.abc123.js").write_text("console.log(1)" * 200)
    settings = Settings(data_root=tmp_path / "data", worker_enabled=False, web_dir=web)
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        hashed = client.get("/_app/immutable/start.abc123.js")
        assert hashed.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert hashed.headers.get("content-encoding") == "gzip", "big text is compressed"
        assert "immutable" not in client.get("/").headers.get("cache-control", "")


def test_json_is_gzipped_when_large_and_images_and_zips_never(tmp_path: Path) -> None:
    from tests.api.conftest import PIN, import_folder
    from tests.synthetic import write_photo

    settings = Settings(
        data_root=tmp_path / "data",
        worker_enabled=False,
        min_free_gb=0,
        argon2_time_cost=1,
        argon2_memory_kib=64,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        client.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
        for n in range(12):
            write_photo(tmp_path / "p" / f"{n}.jpg", seed=n, gps=(48.0 + n / 100, 2.0))
        import_folder(client, tmp_path / "p", "p")
        listing = client.get("/api/assets")
        assert listing.headers.get("content-encoding") == "gzip"
        asset_id = listing.json()["items"][0]["id"]
        assert "content-encoding" not in client.get(f"/api/assets/{asset_id}/thumb").headers
        zipped = client.post("/api/downloads", json={"ids": [asset_id]})
        assert "content-encoding" not in zipped.headers
        assert "content-encoding" not in client.get("/api/health").headers, "small: as is"
        assert client.get("/api/map").json()[0].keys() == {"id", "lat", "lon"}, "shape kept"
