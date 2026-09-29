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
    with TestClient(create_app(settings)) as client:
        assert "app shell" in client.get("/").text
        assert client.get("/_app/main.js").text == "console.log(1)"
        assert "app shell" in client.get("/albums/42").text, "deep links load the app"
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/nope").status_code == 404, "API 404s stay 404s"


def test_without_a_build_only_the_api_is_served(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "data", worker_enabled=False, web_dir=tmp_path / "x")
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200
