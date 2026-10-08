"""The ops command line: export/verify, doctor and backups, on a real library."""

import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant import __main__ as cli
from photo_assistant.api import cli_ops
from photo_assistant.api.cli_ops import human_bytes
from photo_assistant.api.ops_services import RcloneTool, build_backup_service
from photo_assistant.api.settings import Settings
from tests.library_builder import build_library, settings_for

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("cli")
    source = base / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures" / "photos", source)
    build_library(base / "data", source)
    return base / "data"


@pytest.fixture
def settings(built: Path, tmp_path: Path) -> Settings:
    root = tmp_path / "data"
    shutil.copytree(built, root)
    return settings_for(root)


def run(capsys: pytest.CaptureFixture[str], settings: Settings, *argv: str) -> tuple[int, str]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli_ops, "get_settings", lambda: settings)
        code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out + out.err


def test_export_then_verify(
    capsys: pytest.CaptureFixture[str], settings: Settings, tmp_path: Path
) -> None:
    code, out = run(capsys, settings, "export-library", str(tmp_path / "usb" / "library"))
    assert code == 0, out
    assert "Done and verified" in out and "copied" in out and "PA_DATA_ROOT=" in out
    code, out = run(capsys, settings, "verify-library", str(tmp_path / "usb" / "library"))
    assert code == 0 and "Every photo is present and intact." in out
    code, out = run(capsys, settings, "export-library", str(tmp_path / "slim"), "--skip-derived")
    assert code == 0, out


def test_verify_the_configured_library_and_report_damage(
    capsys: pytest.CaptureFixture[str], settings: Settings
) -> None:
    assert run(capsys, settings, "verify-library")[0] == 0
    victim = next(p for p in (settings.data_root / "originals").rglob("*") if p.is_file())
    victim.unlink()
    code, out = run(capsys, settings, "verify-library", "--skip-derived")
    assert code == 1 and "Problems found" in out and victim.name in out


def test_export_that_cannot_complete_says_so(
    capsys: pytest.CaptureFixture[str], settings: Settings, tmp_path: Path
) -> None:
    thumb = next(p for p in (settings.data_root / "derived").rglob("*") if p.is_file())
    thumb.unlink()
    victim = next(p for p in (settings.data_root / "originals").rglob("*") if p.is_file())
    victim.unlink()
    code, out = run(capsys, settings, "export-library", str(tmp_path / "copy"))
    assert code == 1 and "Run the same command again" in out


def test_errors_are_one_line_and_exit_2(
    capsys: pytest.CaptureFixture[str], settings: Settings, tmp_path: Path
) -> None:
    code, out = run(capsys, settings, "export-library", str(settings.data_root / "inside"))
    assert code == 2 and "Error: the destination must be outside the library" in out
    code, out = run(capsys, settings, "verify-library", str(tmp_path / "nowhere"))
    assert code == 2 and "no library" in out


def test_doctor(capsys: pytest.CaptureFixture[str], settings: Settings) -> None:
    code, out = run(capsys, settings, "doctor")
    assert "Photo Assistant doctor" in out and "iPhone HEIC photos" in out
    assert "Library database: integrity check passed" in out
    assert code == 0, out


@pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing")
def test_backup_commands(
    capsys: pytest.CaptureFixture[str], settings: Settings, tmp_path: Path
) -> None:
    password = tmp_path / "secret" / "pw"
    password.parent.mkdir()
    password.write_text("pw\n")
    (tmp_path / "disk").mkdir()
    code, out = run(capsys, settings, "backup", "list")
    assert code == 0 and "No backup targets yet" in out
    code, out = run(
        capsys,
        settings,
        "backup",
        "add",
        "Disk",
        str(tmp_path / "disk" / "photos"),
        "--password-file",
        str(password),
        "--schedule",
        "weekly sun 03:00",
        "--keep-daily",
        "3",
    )
    assert code == 0 and "Added backup target 1 'Disk'" in out
    code, out = run(capsys, settings, "backup", "run", "1")
    assert code == 0 and "backup succeeded" in out and "snapshot" in out, out
    code, out = run(capsys, settings, "backup", "list")
    assert "ok" in out and "Disk" in out and "weekly sun 03:00" in out
    code, out = run(capsys, settings, "backup", "check", "1", "--read-data", "10%")
    assert code == 0 and "read 10%" in out
    code, out = run(capsys, settings, "backup", "restore-test", "1", "--sample", "3")
    assert code == 0 and "every hash matches" in out
    assert run(capsys, settings, "backup", "run-due")[1].strip() == "Nothing is due."
    assert "disabled" in run(capsys, settings, "backup", "disable", "1")[1]
    assert "disabled" in run(capsys, settings, "backup", "list")[1]
    assert "enabled" in run(capsys, settings, "backup", "enable", "1")[1]
    password.write_text("changed\n")
    code, out = run(capsys, settings, "backup", "run", "1")
    assert code == 1 and "wrong password" in out
    code, out = run(capsys, settings, "backup", "list")
    assert "FAILED" in out and "last error: wrong password" in out
    code, out = run(capsys, settings, "backup", "run", "99")
    assert code == 2 and "no backup target 99" in out
    code, out = run(
        capsys, settings, "backup", "add", "X", "/x", "--password-file", str(password),
        "--schedule", "sometimes",
    )  # fmt: skip
    assert code == 2 and "unknown schedule" in out


def test_backup_without_a_library(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out = run(capsys, settings_for(tmp_path / "empty"), "backup", "list")
    assert code == 2 and "No library" in out


def test_backup_run_due_prints_each_run(
    capsys: pytest.CaptureFixture[str], settings: Settings, tmp_path: Path
) -> None:
    password = tmp_path / "pw"
    password.write_text("pw\n")
    run(capsys, settings, "backup", "add", "Gone", "/media/none/Disk/photos",
        "--password-file", str(password), "--schedule", "hourly")  # fmt: skip
    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with sqlite3.connect(settings.data_root / "library.db") as conn:
        conn.execute("UPDATE backup_target SET created_at = ?", (two_hours_ago,))
    code, out = run(capsys, settings, "backup", "run-due")
    assert code == 1 and "backup failed" in out and "plug in" in out


def test_the_ops_commands_are_part_of_the_one_command_table() -> None:
    parser = cli.build_parser()
    assert "import" not in {command.name for command in cli_ops.COMMANDS}
    assert set(cli_ops.COMMANDS) < set(cli.COMMANDS)
    assert parser.parse_args(["backup", "run", "3"]).target_id == 3


def test_human_bytes() -> None:
    assert human_bytes(None) == "-"
    assert human_bytes(512) == "512 B"
    assert human_bytes(1_500_000) == "1.5 MB"
    assert human_bytes(3 * 1000**5) == "3000.0 TB"


def test_backup_from_the_command_line_uses_the_configured_rclone(
    capsys: pytest.CaptureFixture[str], settings: Settings, tmp_path: Path
) -> None:
    """The server passes PA_RCLONE_BINARY / PA_RCLONE_CONFIG to its backup service; a backup
    run from the command line must reach an rclone remote the same way."""
    settings.integrations.rclone_binary = "/opt/rclone/rclone"
    settings.integrations.rclone_config = tmp_path / "rclone.conf"
    seen: list[RcloneTool] = []
    real = build_backup_service

    def spy(*args: object, **kwargs: object) -> object:
        seen.append(kwargs["rclone"])  # type: ignore[arg-type]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli_ops, "build_backup_service", spy)
        code, _ = run(capsys, settings, "backup", "list")
    assert code == 0
    assert seen == [RcloneTool("/opt/rclone/rclone", tmp_path / "rclone.conf")]
