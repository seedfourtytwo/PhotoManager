"""What the Proton Drive and rclone routes answer when the provider's tool cannot do it, on
the real app: status and sentence are the contract (the web app shows the sentence).

Written before the pull errors were split into "waiting cannot fix it" (a DomainError, answered
by the one handler) and "may pass" (answered 503 by the app as well): every answer here is the
same before and after."""

import stat
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.adapters import proton_drive, rclone_sync
from photo_assistant.adapters.tool_runner import ToolTimeoutError
from photo_assistant.api.main import create_app
from photo_assistant.api.settings import IntegrationSettings
from tests.api.conftest import BASE, PIN, make_settings, refusal
from tests.proton_cloud import Cloud

SIGNED_OUT = (
    503,
    {
        "detail": "Proton Drive is not signed in on this machine: "
        "run 'proton-drive auth login' and try again"
    },
)
NO_PROTON_TOOL = (
    503,
    {"detail": "Proton Drive's tool (proton-drive) is not installed on this machine"},
)
NO_RCLONE = (503, {"detail": "rclone is not installed on this machine (sudo apt install rclone)"})


Start = Callable[..., TestClient]  # start(proton=..., rclone=...): the app's signed-in admin


def _script(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def start(tmp_path: Path) -> Iterator[Start]:
    """Start the app with these tools; answers its signed-in admin."""
    clients: list[TestClient] = []

    def started(*, proton: Path | None = None, rclone: Path | None = None) -> TestClient:
        tools = IntegrationSettings(
            proton_drive_binary=str(proton or tmp_path / "no-proton-drive"),
            rclone_binary=str(rclone or tmp_path / "no-rclone"),
        )
        settings = make_settings(tmp_path / f"data{len(clients)}", integrations=tools)
        client = TestClient(create_app(settings), base_url=BASE)
        client.__enter__()
        clients.append(client)
        created = client.post("/api/setup", json={"username": "c", "display_name": "C", "pin": PIN})
        assert created.status_code == 201, created.text
        return client

    yield started
    for client in clients:
        client.__exit__(None, None, None)


def _proton_answers(admin: TestClient) -> list[tuple[int, object]]:
    """Every Proton route that asks Proton something: list, new folder, new source."""
    return [
        refusal(admin.get("/api/proton/folders", params={"path": "/my-files"})),
        refusal(admin.post("/api/proton/folders", json={"parent": "/my-files", "name": "New"})),
        refusal(admin.post("/api/proton/sources", json={"label": "x", "path": "/my-files"})),
    ]


def test_signed_out_of_proton(
    start: Start, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.state["signed_in"] = False
    cloud.save()
    admin = start(proton=cloud.binary)

    assert _proton_answers(admin) == [SIGNED_OUT] * 3
    assert refusal(admin.post("/api/proton/sources", json={"label": "x", "path": "/photos"})) == (
        SIGNED_OUT
    )
    assert admin.get("/api/proton").json() == {"ready": False, "problem": SIGNED_OUT[1]["detail"]}
    assert admin.get("/api/sources").json() == []


def test_a_proton_folder_that_is_not_there(
    start: Start, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud = Cloud(tmp_path, monkeypatch)
    cloud.folder("/", {"type": "folder", "uid": "m", "name": "my-files"})
    cloud.folder("/my-files")
    admin = start(proton=cloud.binary)
    missing = (404, {"detail": "folder '/my-files/Nope' not found on Proton Drive"})

    assert refusal(admin.get("/api/proton/folders", params={"path": "/my-files/Nope"})) == missing
    made = admin.post("/api/proton/folders", json={"parent": "/my-files/Nope", "name": "x"})
    assert refusal(made) == missing
    added = admin.post("/api/proton/sources", json={"label": "x", "path": "/my-files/Nope"})
    assert refusal(added) == missing


def test_protons_tool_is_not_installed(start: Start) -> None:
    admin = start()
    assert _proton_answers(admin) == [NO_PROTON_TOOL] * 3
    assert admin.get("/api/proton").json() == {
        "ready": False,
        "problem": NO_PROTON_TOOL[1]["detail"],
    }


def test_proton_fails_for_a_reason_that_may_pass(start: Start, tmp_path: Path) -> None:
    offline = _script(tmp_path / "offline", 'echo "network error: connection reset" >&2; exit 1')
    admin = start(proton=offline)
    answer = (503, {"detail": "Proton Drive: network error: connection reset"})

    assert _proton_answers(admin) == [answer] * 3
    assert admin.get("/api/proton").json() == {"ready": False, "problem": answer[1]["detail"]}


def test_proton_answers_with_something_unreadable(start: Start, tmp_path: Path) -> None:
    admin = start(proton=_script(tmp_path / "garbled", "echo '<html>maintenance</html>'"))
    listed = admin.get("/api/proton/folders", params={"path": "/my-files"})
    assert refusal(listed) == (
        503,
        {"detail": "Proton Drive answered with something unreadable"},
    )


def test_proton_takes_too_long_to_answer(
    start: Start, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proton_drive, "_ASK_TIMEOUT", 0.2)
    admin = start(proton=_script(tmp_path / "slow", "sleep 5"))
    listed = admin.get("/api/proton/folders", params={"path": "/my-files"})
    assert refusal(listed) == (
        503,
        {"detail": "Proton Drive took too long to answer; try again later"},
    )


def test_rclone_is_not_installed(start: Start) -> None:
    admin = start()
    assert refusal(admin.get("/api/remote-sources/remotes")) == NO_RCLONE
    added = admin.post("/api/remote-sources", json={"label": "x", "remote": "mega"})
    assert refusal(added) == NO_RCLONE


def test_rclone_takes_too_long_to_list_its_remotes(
    start: Start, monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_slow(binary: str, config: Path | None) -> list[str]:
        raise ToolTimeoutError("'rclone' did not finish within 20 s")

    monkeypatch.setattr(rclone_sync, "read_remotes", too_slow)
    admin = start()
    slow = (503, {"detail": "rclone took too long to list its remotes; try again"})

    assert refusal(admin.get("/api/remote-sources/remotes")) == slow
    added = admin.post("/api/remote-sources", json={"label": "x", "remote": "mega"})
    assert refusal(added) == slow
