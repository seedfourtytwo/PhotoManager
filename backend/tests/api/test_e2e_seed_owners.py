"""scripts/e2e_seed.py imports its folders before any account exists. In the seeded library
every folder must have an owner all the same: "private" compares the marker with the owner,
so on an ownerless folder the mark would hide a photo from nobody."""

from pathlib import Path

import pytest
from scripts import e2e_seed

from photo_assistant.api.services import build_services
from tests.library_builder import settings_for
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


def test_the_seeded_e2e_library_has_no_ownerless_folder(tmp_path: Path) -> None:
    for n, (folder, _) in enumerate(e2e_seed.SOURCES):
        write_photo(tmp_path / "src" / folder / "a.jpg", seed=n)
    services = build_services(settings_for(tmp_path / "data"))
    try:
        sources = e2e_seed.import_sources(services, tmp_path / "src")
        before = {s.label: s.owner_id for s in services.repo.list_sources()}
        assert set(before.values()) == {None}, "no account yet: the 'none' snapshot"

        e2e_seed.seed_people(services, sources, tmp_path / "data" / "library.db")

        users = {u.username: u.id for u in services.repo.list_users()}
        owners = {s.label: s.owner_id for s in services.repo.list_sources()}
    finally:
        services.close()
    assert owners == {
        "Phone": users["admin"],
        "Old hard disk": users["admin"],
        "Partner": users["partner"],
    }
