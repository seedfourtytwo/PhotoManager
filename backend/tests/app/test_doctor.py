"""``just doctor``: the checklist logic with a fake probe, then the real probe on this machine."""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import open_database
from photo_assistant.adapters.system_probe import LocalSystemProbe
from photo_assistant.api.ops_services import doctor_sample
from photo_assistant.app.doctor import (
    DoctorConfig,
    Level,
    exit_code,
    render,
    run_doctor,
    version_tuple,
)
from photo_assistant.domain.backup import GB


@dataclass
class FakeProbe:
    versions: dict[str, str | None] = field(
        default_factory=lambda: {"exiftool": "12.76", "restic": "0.16.4", "rclone": "1.60.1"}
    )
    vips: str | None = "8.15.1"
    decode: str | None = None
    free: int = 500 * GB
    writable: str | None = None
    integrity: str = "ok"
    models: bool = False

    def tool_version(self, tool: str) -> str | None:
        return self.versions.get(tool)

    def libvips_version(self) -> str | None:
        return self.vips

    def decode_error(self, sample: Path) -> str | None:
        return self.decode

    def free_bytes(self, folder: Path) -> int:
        return self.free

    def writable_error(self, folder: Path) -> str | None:
        return self.writable

    def database_integrity(self, database: Path) -> str:
        return self.integrity

    def has_models(self, folder: Path) -> bool:
        return self.models


def _levels(probe: FakeProbe, root: Path) -> dict[str, Level]:
    checks = run_doctor(probe, DoctorConfig(root, Path("sample.heic")))
    return {c.name: c.level for c in checks}


def test_a_healthy_machine(tmp_path: Path) -> None:
    (tmp_path / "library.db").write_bytes(b"x")
    checks = run_doctor(FakeProbe(), DoctorConfig(tmp_path, Path("sample.heic")))
    assert {c.level for c in checks} == {Level.OK, Level.OPTIONAL}
    assert exit_code(checks) == 0
    text = render(checks)
    assert "[ok  ] ExifTool: 12.76" in text and "All required checks passed." in text
    assert "[--  ] AI models" in text


def test_missing_required_tools_fail_with_the_apt_command(tmp_path: Path) -> None:
    probe = FakeProbe(versions={"exiftool": None}, vips=None, decode="heif: no decoder")
    checks = run_doctor(probe, DoctorConfig(tmp_path, Path("s")))
    assert exit_code(checks) == 1
    text = render(checks)
    assert "fix: sudo apt install libimage-exiftool-perl" in text
    assert "fix: sudo apt install libheif-plugin-libde265" in text
    assert "3 problem(s) to fix." in text
    levels = {c.name: c.level for c in checks}
    assert levels["restic (backups)"] is Level.OPTIONAL, "backups are optional to start"


def test_old_versions_warn(tmp_path: Path) -> None:
    levels = _levels(
        FakeProbe(versions={"exiftool": "11.88", "restic": "0.9.6"}, vips="8.9.1"), tmp_path
    )
    assert levels["ExifTool"] is Level.WARN
    assert levels["libvips"] is Level.WARN
    assert levels["restic (backups)"] is Level.WARN


def test_disk_space_thresholds(tmp_path: Path) -> None:
    assert _levels(FakeProbe(free=5 * GB), tmp_path)["Free disk space"] is Level.FAIL
    assert _levels(FakeProbe(free=15 * GB), tmp_path)["Free disk space"] is Level.WARN
    assert _levels(FakeProbe(free=25 * GB), tmp_path)["Free disk space"] is Level.OK


def test_data_folder_and_database_problems(tmp_path: Path) -> None:
    (tmp_path / "library.db").write_bytes(b"x")
    levels = _levels(FakeProbe(writable="Permission denied", integrity="page 3: bad"), tmp_path)
    assert levels["Data folder"] is Level.FAIL
    assert levels["Library database"] is Level.FAIL
    fresh = run_doctor(FakeProbe(models=True), DoctorConfig(tmp_path / "new", Path("s")))
    by_name = {c.name: c for c in fresh}
    assert "will be created" in by_name["Data folder"].detail
    assert "none yet" in by_name["Library database"].detail
    assert by_name["AI models"].level is Level.OK


def test_version_tuple() -> None:
    assert version_tuple("12.76") == (12, 76)
    assert version_tuple("0.16.4") == (0, 16, 4)


# --- the real probe (integration) ---------------------------------------------------------


@pytest.mark.integration
def test_real_probe_on_this_machine(tmp_path: Path) -> None:
    probe = LocalSystemProbe()
    if shutil.which("exiftool"):
        assert version_tuple(probe.tool_version("exiftool") or "0") >= (12, 15)
    assert probe.tool_version("surely-not-installed-tool") is None
    assert probe.tool_version("false") is None
    assert version_tuple(probe.libvips_version() or "0") >= (8, 12)
    assert probe.decode_error(doctor_sample()) is None, "HEIC decodes with the real renderer"
    broken = tmp_path / "broken.heic"
    broken.write_bytes(b"not an image")
    assert probe.decode_error(broken)
    assert probe.free_bytes(tmp_path / "not" / "yet") > 0
    assert probe.writable_error(tmp_path) is None
    assert probe.writable_error(tmp_path / "new" / "data") is None
    assert not probe.has_models(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "clip.onnx").write_bytes(b"")
    assert probe.has_models(tmp_path / "models")


@pytest.mark.integration
def test_real_probe_database_integrity(tmp_path: Path) -> None:
    probe = LocalSystemProbe()
    open_database(tmp_path / "library.db").close()
    assert probe.database_integrity(tmp_path / "library.db") == "ok"
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"SQLite format 3\x00" + b"\xff" * 5000)
    assert probe.database_integrity(garbage) != "ok"
    assert probe.database_integrity(tmp_path / "missing.db") != "ok"


def test_the_bundled_sample_is_the_synthetic_fixture() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "photos" / "IMG_1004.HEIC"
    assert doctor_sample().read_bytes() == fixture.read_bytes()
