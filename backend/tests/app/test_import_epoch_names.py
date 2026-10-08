"""Importing a photo named with a Unix timestamp on a machine in a zone with summer time:
the photo lands at the local time of its own day, whenever the file was saved."""

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from photo_assistant.api.services import build_services
from photo_assistant.domain.capture_time import DateSource
from tests.library_builder import settings_for
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


@pytest.fixture
def in_berlin(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _saved(path: Path, when: datetime) -> None:
    os.utime(path, (when.timestamp(), when.timestamp()))


@pytest.mark.usefixtures("in_berlin")
def test_a_winter_photo_downloaded_in_summer_is_dated_on_its_own_evening(tmp_path: Path) -> None:
    taken = datetime(2020, 1, 15, 22, 30, tzinfo=UTC)  # 23:30 in Berlin, winter time
    source = tmp_path / "source"
    source.mkdir()
    photo = write_photo(source / f"FB_IMG_{int(taken.timestamp()) * 1000}.jpg", seed=1)
    _saved(photo, datetime(2020, 7, 1, 9, 0, tzinfo=UTC))

    services = build_services(settings_for(tmp_path / "data"))
    try:
        added = services.repo.add_source("Downloads", str(source))
        services.importer.run(added.id)
        asset_id = services.repo.asset_id_for_source_path(added.id, photo.name)
        assert asset_id is not None
        asset = services.repo.get_asset(asset_id)
    finally:
        services.close()

    assert asset is not None and asset.date_source is DateSource.FILENAME
    assert asset.taken_at == datetime(2020, 1, 15, 23, 30), "not 00:30 on the 16th"
    assert asset.tz_offset_minutes == 60
