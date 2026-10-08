"""Leftovers of a crash are cleared when the server starts, and only then."""

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.services import build_services
from photo_assistant.domain.job_queue import CLAIM_STALE_AFTER
from tests.api.conftest import BASE, make_settings, services_of


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


def test_the_server_start_requeues_only_jobs_whose_process_is_gone(tmp_path: Path) -> None:
    """The server and CLI commands share the queue: a job a live `import` command is running
    must not be started a second time; one whose process died long ago is queued again."""
    settings = make_settings(tmp_path / "data")
    cli = build_services(settings)
    try:
        now = cli.clock.now()
        dead = cli.repo.enqueue("preview", {"asset_id": 1})
        live = cli.repo.enqueue("preview", {"asset_id": 2})
        long_ago = now - CLAIM_STALE_AFTER - timedelta(seconds=1)
        assert cli.repo.claim_next_job(long_ago, owner="cli-dead") is not None
        assert cli.repo.claim_next_job(now, owner=cli.worker.owner) is not None
        with TestClient(create_app(settings), base_url=BASE):
            jobs = {job["id"]: (job["status"], job["attempts"]) for job in cli.repo.list_jobs()}
        assert jobs == {dead: ("queued", 1), live: ("running", 1)}
    finally:
        cli.close()


def test_the_server_and_a_cli_command_claim_jobs_under_different_names(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data")
    cli = build_services(settings)
    try:
        with TestClient(create_app(settings), base_url=BASE) as client:
            server = services_of(client).worker.owner
        assert server.startswith("server-") and cli.worker.owner.startswith("cli-")
    finally:
        cli.close()
