"""Leftovers of a crash are cleared when the server starts, and only then."""

from pathlib import Path

from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.services import build_services
from tests.api.conftest import BASE, make_settings


def test_only_the_server_start_sweeps_half_written_files_never_a_cli_command(
    tmp_path: Path,
) -> None:
    """A CLI command (set-pin, sources, …) builds the services while the server may be in the
    middle of an upload: it must leave the server's ``upload-*.partial`` alone."""
    settings = make_settings(tmp_path / "data")
    partial = tmp_path / "data" / "tmp" / "upload-abc.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"half an upload")
    build_services(settings).close()
    assert partial.exists(), "building services (what every CLI command does) swept it"
    with TestClient(create_app(settings), base_url=BASE):
        assert not partial.exists(), "the server start clears leftovers of a crash"
