"""ProtonMirror against the stand-in CLI: the encrypted backup folder is copied to Proton
Drive, files the backup dropped are removed there, and nothing else is ever touched."""

import json
from pathlib import Path

import pytest

from photo_assistant.adapters.proton_mirror import ProtonMirror
from photo_assistant.ports.backup import MirrorError, MirrorReport, MirrorSignInError
from tests.conftest import snapshot_tree
from tests.proton_cloud import Cloud

REMOTE = "/my-files/Backups"
COPY = f"{REMOTE}/photo-assistant-backup"


class World:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.cloud = Cloud(tmp_path, monkeypatch)
        self.cloud.folder("/my-files", {"type": "folder", "uid": "b", "name": "Backups"})
        self.cloud.folder(REMOTE, self.cloud.image("mine", "holiday.jpg"))
        self.repo = tmp_path / "disk" / "photo-assistant-backup"
        for name, content in {
            "config": "cfg",
            "keys/k1": "key",
            "snapshots/s1": "snap one",
            "index/i1": "index one",
            "data/ab/pack1": "pack one",
            "data/cd/pack2": "pack two",
        }.items():
            self.write(name, content)
        (self.repo / "locks").mkdir()
        self.state = tmp_path / "mirror" / "1.json"
        self.mirror = ProtonMirror(self.cloud.drive)

    def write(self, name: str, content: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def run(self) -> MirrorReport:
        return self.mirror.mirror(self.repo, REMOTE, self.state)

    def remote(self) -> dict[str, str]:
        """relative path → content of every file in the copy on Proton."""
        tree = json.loads(self.cloud.state_file.read_text())["tree"]
        found = {}
        for folder, entries in tree.items():
            if folder == COPY or folder.startswith(COPY + "/"):
                for e in entries:
                    if e["type"] == "file":
                        relative = f"{folder}/{e['name']}".removeprefix(COPY + "/")
                        found[relative] = Path(e["source"]).read_text()
        return found

    def local(self) -> dict[str, str]:
        return {
            str(p.relative_to(self.repo)): p.read_text()
            for p in self.repo.rglob("*")
            if p.is_file()
        }

    def verbs(self) -> set[tuple[str, ...]]:
        return {tuple(call[:2]) for call in self.cloud.calls()}

    def touched(self) -> list[str]:
        """Every remote path a trash or delete command named."""
        return [
            arg
            for call in self.cloud.calls()
            if call[:2] in (["filesystem", "trash"], ["filesystem", "delete"])
            for arg in call[2:]
            if arg.startswith("/")
        ]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, monkeypatch)


def test_the_first_mirror_copies_the_whole_backup_folder(world: World) -> None:
    before = snapshot_tree(world.repo)
    report = world.run()
    assert world.remote() == world.local()
    assert (report.uploaded, report.removed) == (6, 0)
    assert report.bytes_sent == sum(len(c) for c in world.local().values())
    assert snapshot_tree(world.repo) == before, "the mirror never writes to the backup itself"


def test_an_unchanged_backup_sends_nothing_and_removes_nothing(world: World) -> None:
    world.run()
    report = world.run()
    assert (report.uploaded, report.removed, report.bytes_sent) == (0, 0, 0)
    assert world.touched() == []


def test_only_what_is_new_is_sent(world: World) -> None:
    world.run()
    world.write("data/ef/pack3", "pack three")
    world.write("snapshots/s2", "snap two")
    report = world.run()
    assert (report.uploaded, report.removed) == (2, 0)
    assert world.remote() == world.local()


def test_files_the_backup_dropped_are_deleted_for_good_on_proton(world: World) -> None:
    world.run()
    (world.repo / "data" / "ab" / "pack1").unlink()  # as restic's prune does
    (world.repo / "snapshots" / "s1").unlink()
    world.write("snapshots/s2", "snap two")
    report = world.run()
    assert (report.uploaded, report.removed) == (1, 2)
    assert world.remote() == world.local()
    assert json.loads(world.cloud.state_file.read_text())["trash"] == {}, "not left in the trash"
    assert world.run().removed == 0, "and not asked for again"


def test_only_files_inside_the_copy_are_ever_removed(world: World) -> None:
    world.run()
    (world.repo / "data" / "cd" / "pack2").unlink()
    world.run()
    assert world.touched(), "something was removed"
    assert all(p.startswith((COPY + "/", "/trash/")) for p in world.touched())
    tree = json.loads(world.cloud.state_file.read_text())["tree"]
    assert [e["name"] for e in tree[REMOTE] if e["type"] == "file"] == ["holiday.jpg"]
    assert world.verbs() <= {
        ("filesystem", "upload"),
        ("filesystem", "info"),
        ("filesystem", "trash"),
        ("filesystem", "delete"),
        ("filesystem", "list"),
    }


def test_lost_bookkeeping_means_look_at_proton_itself(world: World) -> None:
    world.run()
    (world.repo / "data" / "ab" / "pack1").unlink()
    world.state.unlink()
    report = world.run()
    assert report.removed == 1 and world.remote() == world.local()
    world.state.write_text("{not json")
    (world.repo / "index" / "i1").unlink()
    assert world.run().removed == 1 and world.remote() == world.local()


def test_bookkeeping_for_another_place_is_not_trusted(world: World) -> None:
    world.run()
    world.cloud.state = json.loads(world.cloud.state_file.read_text())
    world.cloud.folder("/my-files/Elsewhere")
    tree: dict[str, list[dict[str, object]]] = world.cloud.state["tree"]  # type: ignore[assignment]
    tree["/my-files"].append({"type": "folder", "uid": "e", "name": "Elsewhere"})
    world.cloud.save()
    report = world.mirror.mirror(world.repo, "/my-files/Elsewhere", world.state)
    assert (report.uploaded, report.removed) == (6, 0)


def test_a_failed_upload_stops_before_anything_is_removed(world: World) -> None:
    world.run()
    (world.repo / "data" / "ab" / "pack1").unlink()
    world.write("data/ef/pack3", "pack three")
    world.cloud.state = json.loads(world.cloud.state_file.read_text())
    world.cloud.state["fail_upload"] = ["pack3"]
    world.cloud.save()
    with pytest.raises(MirrorError, match="1 file"):
        world.run()
    assert "data/ab/pack1" in world.remote(), "nothing is removed while the copy is incomplete"
    world.cloud.state = json.loads(world.cloud.state_file.read_text())
    world.cloud.state["fail_upload"] = []
    world.cloud.save()
    report = world.run()
    assert (report.uploaded, report.removed) == (1, 1) and world.remote() == world.local()


def test_not_signed_in_and_a_missing_folder_say_what_to_do(world: World) -> None:
    with pytest.raises(MirrorError, match="/my-files/Nope"):
        world.mirror.mirror(world.repo, "/my-files/Nope", world.state)
    world.cloud.state["signed_in"] = False
    world.cloud.save()
    with pytest.raises(MirrorSignInError, match="proton-drive auth login"):
        world.run()


@pytest.mark.parametrize("remote", ["/photos", "/trash", "/my-files/../trash", "my-files", ""])
def test_only_a_folder_in_my_files_can_hold_the_copy(world: World, remote: str) -> None:
    with pytest.raises(MirrorError, match="My files"):
        world.mirror.mirror(world.repo, remote, world.state)
    assert world.cloud.calls() == []


def test_a_backup_folder_that_is_not_there_is_refused(world: World, tmp_path: Path) -> None:
    with pytest.raises(MirrorError, match="not found"):
        world.mirror.mirror(tmp_path / "nope", REMOTE, world.state)
