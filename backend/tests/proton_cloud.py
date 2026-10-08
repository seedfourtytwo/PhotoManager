"""A pretend Proton account for tests: the stand-in CLI plus the state file that drives it."""

import json
import stat
import sys
from pathlib import Path

import pytest

from photo_assistant.adapters.proton_drive import ProtonDrive
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.sync import SyncOptions, SyncReport

FAKE = Path(__file__).parent / "fake_proton_drive.py"
OPTIONS = SyncOptions(timeout_seconds=60)
PHOTOS = RemoteConfig.proton("/photos")


class Cloud:
    """The pretend Proton account, and the adapter pointed at it."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = tmp_path / "cloud"
        self.home.mkdir()
        self.state_file = self.home / "state.json"
        self.state: dict[str, object] = {"signed_in": True, "photos": [], "tree": {}}
        self.binary = tmp_path / "proton-drive"
        self.binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setenv("PA_FAKE_PROTON", str(self.state_file))
        self.drive = ProtonDrive(str(self.binary), batch_size=3)
        self.staging = tmp_path / "data" / "staging" / "7"
        self.save()

    def save(self) -> None:
        self.state_file.write_text(json.dumps(self.state))

    def file(self, name: str, content: str | None = None) -> str:
        path = self.home / "blobs" / f"{len(list(self.home.rglob('*')))}-{name}"
        path.parent.mkdir(exist_ok=True)
        path.write_text(content if content is not None else f"pixels of {name}")
        return str(path)

    def photo(
        self, uid: str, name: str, media: str = "image/jpeg", content: str | None = None
    ) -> None:
        photos: list[dict[str, object]] = self.state["photos"]  # type: ignore[assignment]
        photos.append(
            {"uid": uid, "name": name, "mediaType": media, "source": self.file(name, content)}
        )
        self.save()

    def folder(self, path: str, *entries: dict[str, object]) -> None:
        tree: dict[str, list[dict[str, object]]] = self.state["tree"]  # type: ignore[assignment]
        tree[path] = list(entries)
        self.save()

    def image(self, uid: str, name: str, media: str = "image/jpeg") -> dict[str, object]:
        return {
            "type": "file",
            "uid": uid,
            "name": name,
            "mediaType": media,
            "source": self.file(name),
        }

    def calls(self) -> list[list[str]]:
        log = self.home / "calls.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def downloads(self) -> list[list[str]]:
        return [c for c in self.calls() if "download" in c]

    def staged(self) -> list[str]:
        return sorted(
            str(p.relative_to(self.staging)) for p in self.staging.rglob("*") if p.is_file()
        )

    def pull(self, config: RemoteConfig = PHOTOS) -> SyncReport:
        return self.drive.pull(config, self.staging, OPTIONS)
