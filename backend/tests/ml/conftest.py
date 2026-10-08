"""Fixtures for the ML tests: the ML store on the shared in-memory library (``db``, ``repo``)."""

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_database import Database


@pytest.fixture
def store(db: Database) -> SqliteMlStore:
    return SqliteMlStore(db)
