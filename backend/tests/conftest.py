"""Shared fixtures.

`source_guard` enforces rule #1 (originals are sacred): any test that imports from a source
folder must leave it byte-identical. Import tests (M1) take this fixture.

`no_settings_from_the_shell` keeps the developer's own `.env` out: `just` exports it into every
recipe, and the environment beats a test's own values.

`db`, `conn`, `repo` and `clock` are the in-memory library and the fake clock most tests start
from; a test file that needs a different one defines its own under the same name.

`PA_REQUIRE_TOOLS=1` (CI sets it) turns a skip for a missing external tool into a failure, so
a machine that is meant to have every tool can't go green with those tests left out.
"""

import hashlib
import os
import shutil
import sqlite3
from collections.abc import Generator, Iterator
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from tests.fakes import FakeClock

pytest_plugins = ["pytester"]  # tests/unit/test_require_tools.py runs the hooks below

EXTERNAL_TOOLS = ("exiftool", "vips", "restic", "rclone")
_REQUIRE_TOOLS = pytest.StashKey[bool]()


def missing_tool(skip_reason: str) -> str | None:
    """The external tool a skip reason names ("restic missing" -> "restic"), if any."""
    reason = skip_reason.lower()
    return next((tool for tool in EXTERNAL_TOOLS if tool in reason), None)


def pytest_configure(config: pytest.Config) -> None:
    # read here: `no_settings_from_the_shell` clears every PA_* variable before the tests run
    config.stash[_REQUIRE_TOOLS] = os.environ.get("PA_REQUIRE_TOOLS") == "1"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    plain_skip = report.skipped and not hasattr(report, "wasxfail")
    if plain_skip and item.config.stash[_REQUIRE_TOOLS] and isinstance(report.longrepr, tuple):
        reason = str(report.longrepr[2]).removeprefix("Skipped: ")
        if tool := missing_tool(reason):
            report.outcome = "failed"
            report.longrepr = f"PA_REQUIRE_TOOLS=1 but {tool} is not installed ({reason})"
    return report


def snapshot_tree(root: Path) -> dict[str, tuple[str, int, int]]:
    """Every file and folder under root → (sha256 or "dir", mtime_ns, permission bits)."""
    result: dict[str, tuple[str, int, int]] = {}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        digest = "dir" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(root))] = (digest, stat.st_mtime_ns, stat.st_mode)
    return result


@pytest.fixture(scope="session", autouse=True)
def no_settings_from_the_shell() -> Iterator[None]:
    """The run starts with no PA_* variable set; each test sets the ones it needs itself.

    Session-wide so that module-scoped fixtures, which build before any per-test one, are covered.
    """
    with pytest.MonkeyPatch.context() as patch:
        for name in [name for name in os.environ if name.startswith("PA_")]:
            patch.delenv(name)
        yield


@pytest.fixture
def source_guard(tmp_path: Path) -> Iterator[Path]:
    """A source folder that must be unchanged when the test finishes."""
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parent / "fixtures" / "photos", source)
    before = snapshot_tree(source)
    yield source
    after = snapshot_tree(source)
    assert after == before, "a source folder was modified — originals are sacred"


@pytest.fixture
def db() -> Iterator[Database]:
    """An empty, migrated library database in memory."""
    database = Database.open(":memory:")
    yield database
    database.close()


@pytest.fixture
def conn(db: Database) -> sqlite3.Connection:
    """The connection of ``db``, for a test that reads or prepares rows with plain SQL."""
    return db.writer


@pytest.fixture
def repo(db: Database) -> SqliteRepository:
    return SqliteRepository(db)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
