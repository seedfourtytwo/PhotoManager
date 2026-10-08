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

    def add_remote_source(self, label: str, config: RemoteConfig, staging_root: Path) -> int:
        new_id = len(self.configs) + 1
        self.configs[new_id] = config
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
    pulls: list[tuple[RemoteConfig, Path]] = field(default_factory=list)
    remotes: list[str] = field(default_factory=lambda: ["mega", "proton"])

    def pull(self, remote: RemoteConfig, staging: Path, options: SyncOptions) -> SyncReport:
        self.pulls.append((remote, staging))
        if self.fail:
            raise self.fail
        return SyncReport(copied=2, errors=1, error_messages=("x.jpg: broken",))

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
        world.remotes, world.sync, world.staging, "MEGA", {"remote": "mega", "path": "Camera"}
    )
    assert world.remotes.configs[source_id] == RemoteConfig("mega", "Camera")
    with pytest.raises(RemoteConfigError, match="rclone config"):
        add_remote_source(world.remotes, world.sync, world.staging, "x", {"remote": "mgea"})
    with pytest.raises(RemoteConfigError):
        add_remote_source(world.remotes, world.sync, world.staging, "x", {"remote": "-x"})


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
    first = add_proton_source(remotes, account, tmp_path, "Photos", "/photos")
    second = add_proton_source(remotes, account, tmp_path, "Trips", "/my-files/Trips")
    assert remotes.configs[first] == RemoteConfig.proton("/photos")
    assert remotes.configs[second] == RemoteConfig.proton("/my-files/Trips")
    assert account.asked == ["check", "/my-files/Trips"]
    with pytest.raises(SyncNotFoundError):
        add_proton_source(remotes, account, tmp_path, "x", "/my-files/Nope")
    with pytest.raises(RemoteConfigError):
        add_proton_source(remotes, account, tmp_path, "x", "/trash")
    assert len(remotes.configs) == 2
