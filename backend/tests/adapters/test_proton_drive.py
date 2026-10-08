"""ProtonDrive against a stand-in CLI (tests/fake_proton_drive.py): what is fetched, what is
never fetched twice, what happens when Proton or the sign-in fails."""

import json
from pathlib import Path

import pytest

from photo_assistant.adapters.proton_drive import ProtonDrive
from photo_assistant.domain.remote_source import RemoteConfig
from photo_assistant.ports.sync import SyncAuthError, SyncError, SyncNotFoundError
from tests.proton_cloud import OPTIONS, PHOTOS, Cloud


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Cloud:
    return Cloud(tmp_path, monkeypatch)


# --- the Photos section ---------------------------------------------------------------------------


def test_photos_are_fetched_in_batches_and_videos_never(cloud: Cloud) -> None:
    for n in range(5):
        cloud.photo(f"p{n}", f"IMG_{n}.jpg")
    cloud.photo("v1", "clip.mp4", media="video/mp4")
    report = cloud.pull()
    assert (report.copied, report.unchanged, report.errors) == (5, 0, 0)
    assert report.bytes_transferred == sum(len(f"pixels of IMG_{n}.jpg") for n in range(5))
    assert cloud.staged() == [f"IMG_{n}.jpg" for n in range(5)]
    sizes = [sum(a.startswith("/photos/") for a in call) for call in cloud.downloads()]
    assert sizes == [3, 2], "batches of three"
    assert not any("/photos/v1" in call for call in cloud.downloads())


def test_a_second_pull_fetches_nothing_and_a_new_photo_only_itself(cloud: Cloud) -> None:
    cloud.photo("p1", "a.jpg")
    cloud.photo("p2", "b.jpg")
    cloud.pull()
    again = cloud.pull()
    assert (again.copied, again.unchanged) == (0, 2)
    assert len(cloud.downloads()) == 1, "no download command at all the second time"
    cloud.photo("p3", "c.jpg")
    third = cloud.pull()
    assert (third.copied, third.unchanged) == (1, 2)
    assert (
        cloud.downloads()[-1].count("/photos/p3") == 1 and "/photos/p1" not in cloud.downloads()[-1]
    )


def test_two_photos_with_the_same_name_are_both_kept(cloud: Cloud) -> None:
    cloud.photo("p1", "IMG_0001.jpg", content="first")
    cloud.photo("p2", "IMG_0001.jpg", content="second")
    cloud.pull()
    assert cloud.staged() == ["IMG_0001 (1).jpg", "IMG_0001.jpg"]
    assert {(cloud.staging / n).read_text() for n in cloud.staged()} == {"first", "second"}


def test_a_photo_already_in_staging_under_that_name_is_not_overwritten(cloud: Cloud) -> None:
    cloud.photo("p1", "a.jpg", content="old")
    cloud.pull()
    cloud.photo("p2", "a.jpg", content="new")
    cloud.pull()
    assert (cloud.staging / "a.jpg").read_text() == "old"
    assert (cloud.staging / "a (1).jpg").read_text() == "new"


def test_a_photo_that_fails_is_reported_and_tried_again_next_time(cloud: Cloud) -> None:
    for n in range(3):
        cloud.photo(f"p{n}", f"{n}.jpg")
    cloud.state["fail"] = ["p1"]
    cloud.save()
    report = cloud.pull()
    assert (report.copied, report.errors) == (2, 1)
    assert report.partial and "1.jpg" in report.error_messages[0]
    assert cloud.staged() == ["0.jpg", "2.jpg"], "nothing twice after the one-by-one retry"
    cloud.state["fail"] = []
    cloud.save()
    healed = cloud.pull()
    assert (healed.copied, healed.unchanged, healed.errors) == (1, 2, 0)
    assert cloud.staged() == ["0.jpg", "1.jpg", "2.jpg"]


def test_a_batch_the_tool_crashes_on_is_fetched_one_by_one(cloud: Cloud) -> None:
    for n in range(3):
        cloud.photo(f"p{n}", f"{n}.jpg")
    cloud.state["crash_on_batch"] = True
    cloud.save()
    report = cloud.pull()
    assert (report.copied, report.errors) == (3, 0)
    assert cloud.staged() == ["0.jpg", "1.jpg", "2.jpg"]


def test_an_interrupted_pull_resumes_where_it_stopped(cloud: Cloud) -> None:
    for n in range(4):
        cloud.photo(f"p{n}", f"{n}.jpg")
    cloud.pull()
    manifest = cloud.staging.parent / "7.proton.json"
    kept = json.loads(manifest.read_text())
    kept["fetched"] = [u for u in kept["fetched"] if u != "p3"]  # as if it stopped before p3
    manifest.write_text(json.dumps(kept))
    (cloud.staging / "3.jpg").unlink()
    report = cloud.pull()
    assert (report.copied, report.unchanged) == (1, 3)


def test_a_damaged_bookkeeping_file_means_fetch_again_never_lose(cloud: Cloud) -> None:
    cloud.photo("p1", "a.jpg")
    cloud.pull()
    (cloud.staging.parent / "7.proton.json").write_text("{not json")
    report = cloud.pull()
    assert report.copied == 1 and cloud.staged() == ["a (1).jpg", "a.jpg"]


def test_no_leftover_working_folders_and_nothing_but_reads(cloud: Cloud) -> None:
    cloud.photo("p1", "a.jpg")
    cloud.pull()
    assert sorted(p.name for p in cloud.staging.parent.iterdir()) == ["7", "7.proton.json"]
    verbs = {tuple(call[:2]) for call in cloud.calls()}
    assert verbs == {("photo", "timeline"), ("photo", "download")}


# --- Drive folders --------------------------------------------------------------------------------


def test_a_drive_folder_is_walked_keeping_its_structure_and_only_photos(cloud: Cloud) -> None:
    cloud.folder(
        "/my-files/Trips",
        cloud.image("f1", "top.jpg"),
        {
            "type": "file",
            "uid": "d1",
            "name": "tickets.pdf",
            "mediaType": "application/pdf",
            "source": cloud.file("t"),
        },
        {
            "type": "file",
            "uid": "r1",
            "name": "raw.CR2",
            "mediaType": "application/octet-stream",
            "source": cloud.file("r"),
        },
        {"type": "folder", "uid": "s1", "name": "2019 Alps"},
    )
    cloud.folder("/my-files/Trips/2019 Alps", cloud.image("f2", "peak.HEIC", "image/heic"))
    report = cloud.pull(RemoteConfig.proton("/my-files/Trips"))
    assert (report.copied, report.errors) == (3, 0)
    assert cloud.staged() == ["2019 Alps/peak.HEIC", "raw.CR2", "top.jpg"]
    again = cloud.pull(RemoteConfig.proton("/my-files/Trips"))
    assert (again.copied, again.unchanged) == (0, 3)


def test_the_whole_drive_can_be_scanned(cloud: Cloud) -> None:
    cloud.folder(
        "/my-files",
        {"type": "folder", "uid": "s1", "name": "A"},
        cloud.image("f0", "root.png", "image/png"),
    )
    cloud.folder("/my-files/A", cloud.image("f1", "a.jpg"))
    assert cloud.pull(RemoteConfig.proton("/my-files")).copied == 2
    assert cloud.staged() == ["A/a.jpg", "root.png"]


def test_names_proton_could_not_decrypt_are_counted_not_guessed(cloud: Cloud) -> None:
    cloud.folder(
        "/my-files/X",
        cloud.image("f1", "ok.jpg"),
        {"type": "file", "uid": "bad", "name": "?", "mediaType": "image/jpeg", "ok": False},
    )
    report = cloud.pull(RemoteConfig.proton("/my-files/X"))
    assert (report.copied, report.errors) == (1, 1)
    assert "could not be read" in report.error_messages[0]


def test_folder_names_cannot_escape_the_staging_folder(cloud: Cloud) -> None:
    """A folder called ``..`` or ``.`` is not walked at all: as a part of the path handed to
    the tool it would mean the parent (leaving the chosen folder, or walking in circles) or
    the folder itself. It is counted as a problem. Any other odd name is walked and lands
    under a safe name inside staging."""
    cloud.folder(
        "/my-files/X",
        {"type": "folder", "uid": "up", "name": ".."},
        {"type": "folder", "uid": "here", "name": "."},
        {"type": "folder", "uid": "dots", "name": "..."},
        cloud.image("f0", "top.jpg"),
    )
    cloud.folder("/my-files/X/..", cloud.image("f1", "outside.jpg"))
    cloud.folder("/my-files/X/.", cloud.image("f2", "again.jpg"))
    cloud.folder("/my-files/X/...", cloud.image("f3", "a.jpg"))
    report = cloud.pull(RemoteConfig.proton("/my-files/X"))
    assert (report.copied, report.errors) == (2, 2)
    assert all("could not be read" in message for message in report.error_messages)
    assert cloud.staged() == ["_/a.jpg", "top.jpg"]
    everything = {p.name for p in cloud.staging.parent.rglob("*.jpg")}
    assert everything == {"a.jpg", "top.jpg"}, "nothing landed beside staging either"
    asked = [part for call in cloud.calls() for arg in call for part in arg.split("/")]
    assert ".." not in asked and "." not in asked, "the tool is never handed such a path"


# --- when it can't --------------------------------------------------------------------------------


def test_not_signed_in_says_how_to_sign_in(cloud: Cloud) -> None:
    cloud.state["signed_in"] = False
    cloud.save()
    with pytest.raises(SyncAuthError, match="proton-drive auth login"):
        cloud.pull()
    with pytest.raises(SyncAuthError):
        cloud.drive.check()


def test_a_missing_folder_and_a_missing_tool_say_so(cloud: Cloud, tmp_path: Path) -> None:
    with pytest.raises(SyncNotFoundError, match="/my-files/Nope"):
        cloud.pull(RemoteConfig.proton("/my-files/Nope"))
    absent = ProtonDrive(str(tmp_path / "no-such-binary"))
    with pytest.raises(SyncError, match="not installed"):
        absent.pull(PHOTOS, cloud.staging, OPTIONS)


def test_check_passes_when_signed_in_and_folders_lists_sub_folders(cloud: Cloud) -> None:
    cloud.folder("/", {"type": "folder", "uid": "m", "name": "my-files"})
    cloud.folder(
        "/my-files",
        {"type": "folder", "uid": "b", "name": "Trips"},
        {"type": "folder", "uid": "a", "name": "archive"},
        cloud.image("f", "x.jpg"),
    )
    cloud.drive.check()
    assert cloud.drive.folders("/my-files") == ["archive", "Trips"]
