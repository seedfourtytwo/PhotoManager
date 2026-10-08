"""SyncSource: pull a remote into staging, then import staging like a folder."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.app.import_source import SourceUnavailableError
from photo_assistant.app.sync_source import SyncSource, add_remote_source
from photo_assistant.domain.model import ImportReport, RunStatus, Source
from photo_assistant.domain.remote_source import RemoteConfig, RemoteConfigError
from photo_assistant.ports.sync import (
    SyncAuthError,
    SyncError,
    SyncNotFoundError,
    SyncOptions,
    SyncRateLimitedError,
    SyncReport,
)
from tests.factories import NOW


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class FakeRemotes:
    configs: dict[int, RemoteConfig | Exception] = field(default_factory=dict)
    roots: dict[int, str] = field(default_factory=dict)
    owners: dict[int, int] = field(default_factory=dict)

    def add_remote_source(
        self, label: str, config: RemoteConfig, staging_root: Path, owner_id: int
    ) -> int:
        new_id = len(self.configs) + 1
        self.configs[new_id] = config
        self.owners[new_id] = owner_id
        self.roots[new_id] = str(staging_root / str(new_id))
        return new_id

    def remote_config(self, source_id: int) -> RemoteConfig | None:
        found = self.configs.get(source_id)
        if isinstance(found, Exception):
            raise found
        return found

    def set_root(self, source_id: int, root: str) -> None:
        self.roots[source_id] = root


@dataclass
class FakeSync:
    fail: SyncError | None = None
    report: SyncReport = field(
        default_factory=lambda: SyncReport(copied=2, errors=1, error_messages=("x.jpg: broken",))
    )
    pulls: list[tuple[RemoteConfig, Path]] = field(default_factory=list)
    remotes: list[str] = field(default_factory=lambda: ["mega", "proton"])

    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        self.pulls.append((remote, staging))
        if self.fail:
            raise self.fail
        return self.report

    def list_remotes(self) -> list[str]:
        return self.remotes


@dataclass
class FakeLibrary:
    sources: dict[int, Source] = field(default_factory=dict)
    imports: list[int] = field(default_factory=list)
    saved: list[ImportReport] = field(default_factory=list)

    def get_source(self, source_id: int) -> Source | None:
        return self.sources.get(source_id)

    def run(self, source_id: int) -> tuple[int, ImportReport]:
        self.imports.append(source_id)
        return 42, ImportReport(source_id, RunStatus.DONE)

    def save_import_report(
        self, report: ImportReport, started_at: datetime, finished_at: datetime
    ) -> int:
        self.saved.append(report)
        return 43


@dataclass
class World:
    remotes: FakeRemotes
    sync: FakeSync
    library: FakeLibrary
    use_case: SyncSource
    staging: Path


@pytest.fixture
def world(tmp_path: Path) -> World:
    remotes, sync, library = FakeRemotes(), FakeSync(), FakeLibrary()
    library.sources = {
        1: Source(1, "MEGA", "/old/staging/1", kind="rclone"),
        2: Source(2, "Pictures", "/pictures"),
        3: Source(3, "Off", "/x", enabled=False, kind="rclone"),
    }
    remotes.configs = {1: RemoteConfig("mega", "Photos"), 3: RemoteConfig("mega")}
    use_case = SyncSource(
        sources=library,
        remotes=remotes,
        sync=sync,
        importer=library,
        reports=library,
        clock=FixedClock(),
        staging_root=tmp_path / "staging",
        options=SyncOptions(),
    )
    return World(remotes, sync, library, use_case, tmp_path / "staging")


def test_a_remote_source_is_pulled_into_its_staging_folder_then_imported(world: World) -> None:
    outcome = world.use_case.run(1)
    assert world.sync.pulls == [(RemoteConfig("mega", "Photos"), world.staging / "1")]
    assert world.library.imports == [1]
    assert world.remotes.roots[1] == str(world.staging / "1"), "follows a moved data root"
    assert outcome.run_id == 42
    assert outcome.sync is not None and outcome.sync.partial


def test_a_folder_source_is_just_imported(world: World) -> None:
    outcome = world.use_case.run(2)
    assert world.sync.pulls == []
    assert world.library.imports == [2]
    assert outcome.sync is None


@pytest.mark.parametrize("source_id", [3, 404])
def test_disabled_or_unknown_sources_are_not_pulled(world: World, source_id: int) -> None:
    with pytest.raises(SourceUnavailableError):
        world.use_case.run(source_id)
    assert world.sync.pulls == []


@pytest.mark.parametrize(
    "error", [SyncAuthError("login refused"), SyncRateLimitedError("slow down")]
)
def test_errors_retrying_cannot_fix_are_recorded_not_retried(
    world: World, error: SyncError
) -> None:
    world.sync.fail = error
    outcome = world.use_case.run(1)
    assert world.library.imports == []
    (report,) = world.library.saved
    assert report.status is RunStatus.FAILED
    assert report.message is not None and str(error) in report.message
    assert outcome.run_id == 43


def test_other_sync_errors_are_recorded_and_raised_for_a_retry(world: World) -> None:
    world.sync.fail = SyncError("network hiccup")
    with pytest.raises(SyncError):
        world.use_case.run(1)
    assert world.library.saved[0].status is RunStatus.FAILED


def test_a_damaged_remote_config_is_recorded(world: World) -> None:
    world.remotes.configs[1] = RemoteConfigError("bad remote")
    world.use_case.run(1)
    assert world.sync.pulls == []
    assert "bad remote" in (world.library.saved[0].message or "")


def test_adding_a_remote_source_checks_the_remote_exists(world: World) -> None:
    source_id = add_remote_source(
        world.remotes, world.sync, world.staging, "MEGA", {"remote": "mega", "path": "Camera"}, 5
    )
    assert world.remotes.configs[source_id] == RemoteConfig("mega", "Camera")
    assert world.remotes.owners[source_id] == 5, "the admin who adds it owns it"
    with pytest.raises(RemoteConfigError, match="rclone config"):
        add_remote_source(world.remotes, world.sync, world.staging, "x", {"remote": "mgea"}, 5)
    with pytest.raises(RemoteConfigError):
        add_remote_source(world.remotes, world.sync, world.staging, "x", {"remote": "-x"}, 5)


# --- more than one kind of remote (issue 8) -------------------------------------------------------


def test_each_remote_is_pulled_by_the_tool_for_its_provider(tmp_path: Path) -> None:
    from photo_assistant.app.sync_source import ProviderSync

    rclone, proton = FakeSync(), FakeSync()
    sync = ProviderSync({"rclone": rclone, "proton": proton})
    sync.pull(RemoteConfig.proton("/photos"), tmp_path, SyncOptions())
    sync.pull(RemoteConfig("mega"), tmp_path, SyncOptions())
    assert [c.provider for c, _ in proton.pulls] == ["proton"]
    assert [c.remote for c, _ in rclone.pulls] == ["mega"]
    with pytest.raises(SyncError, match="dropbox"):
        sync.pull(RemoteConfig("x", provider="dropbox"), tmp_path, SyncOptions())


@dataclass
class FakeAccount:
    known: tuple[str, ...] = ("/my-files/Trips",)
    asked: list[str] = field(default_factory=list)

    def check(self) -> None:
        self.asked.append("check")

    def folders(self, path: str) -> list[str]:
        self.asked.append(path)
        if path not in self.known:
            raise SyncNotFoundError(f"folder '{path}' not found on Proton Drive")
        return []

    def create_folder(self, parent: str, name: str) -> str:
        return f"{parent}/{name}"


def test_a_proton_source_is_only_added_for_a_place_that_exists(tmp_path: Path) -> None:
    from photo_assistant.app.sync_source import add_proton_source

    remotes, account = FakeRemotes(), FakeAccount()
    first = add_proton_source(remotes, account, tmp_path, "Photos", "/photos", 5)
    second = add_proton_source(remotes, account, tmp_path, "Trips", "/my-files/Trips", 5)
    assert remotes.configs[first] == RemoteConfig.proton("/photos")
    assert remotes.configs[second] == RemoteConfig.proton("/my-files/Trips")
    assert remotes.owners == {first: 5, second: 5}
    assert account.asked == ["check", "/my-files/Trips"]
    with pytest.raises(SyncNotFoundError):
        add_proton_source(remotes, account, tmp_path, "x", "/my-files/Nope", 5)
    with pytest.raises(RemoteConfigError):
        add_proton_source(remotes, account, tmp_path, "x", "/trash", 5)
    assert len(remotes.configs) == 2


# --- a pull that brought only part of the remote --------------------------------------------------


def test_a_partial_pull_is_imported_and_its_failures_go_to_the_import_history(
    world: World,
) -> None:
    outcome = world.use_case.run(1)
    assert world.library.imports == [1] and outcome.run_id == 42, "what arrived is imported"
    (note,) = world.library.saved
    assert (note.source_id, note.status) == (1, RunStatus.FAILED)
    assert note.message is not None
    assert "1 file could not be downloaded from 'MEGA'" in note.message
    assert "x.jpg: broken" in note.message


def test_a_partial_pull_names_only_its_first_few_failures(world: World) -> None:
    messages = tuple(f"{n}.jpg: broken" for n in range(500))
    world.sync.report = SyncReport(copied=1500, errors=500, error_messages=messages)
    world.use_case.run(1)
    message = world.library.saved[0].message or ""
    assert "500 files could not be downloaded" in message
    assert "0.jpg: broken; 1.jpg: broken; 2.jpg: broken" in message
    assert "3.jpg" not in message and "497 more" in message


def test_a_clean_pull_adds_nothing_to_the_import_history(world: World) -> None:
    world.sync.report = SyncReport(copied=2)
    world.use_case.run(1)
    assert world.library.imports == [1] and world.library.saved == []
