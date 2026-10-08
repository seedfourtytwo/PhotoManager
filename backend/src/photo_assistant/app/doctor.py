"""``just doctor``: is this machine ready to run the library? A checklist with fixes."""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photo_assistant.domain.backup import GB
from photo_assistant.domain.library_paths import DATABASE_FILE
from photo_assistant.ports.system_probe import SystemProbe

MIN_EXIFTOOL = (12, 15)  # pyexiftool's minimum
MIN_LIBVIPS = (8, 12)
MIN_RESTIC = (0, 14)  # Debian bookworm; the adapter is written for it


class Level(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "FAIL"
    OPTIONAL = "--"  # not installed, but only needed for an optional feature


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    level: Level
    detail: str
    fix: str | None = None


@dataclass(frozen=True, slots=True)
class DoctorConfig:
    data_root: Path
    heic_sample: Path
    min_free_bytes: int = 10 * GB


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def _tool(
    name: str, version: str | None, minimum: tuple[int, ...], fix: str, *, optional: bool = False
) -> Check:
    if version is None:
        return Check(name, Level.OPTIONAL if optional else Level.FAIL, "not installed", fix)
    if version_tuple(version) < minimum:
        wanted = ".".join(map(str, minimum))
        return Check(name, Level.WARN, f"{version} is older than {wanted}", fix)
    return Check(name, Level.OK, version)


def _heic(probe: SystemProbe, sample: Path) -> Check:
    error = probe.decode_error(sample)
    if error is None:
        return Check("iPhone HEIC photos", Level.OK, "decode fine")
    return Check(
        "iPhone HEIC photos",
        Level.FAIL,
        f"cannot decode: {error}",
        "sudo apt install libheif-plugin-libde265 (then restart the app)",
    )


def _disk(probe: SystemProbe, config: DoctorConfig) -> Check:
    free = probe.free_bytes(config.data_root)
    detail = f"{free / GB:.1f} GB free"
    if free < config.min_free_bytes:
        fix = "free up space or move the library to a bigger disk (docs/guides/move-to-server.md)"
        return Check("Free disk space", Level.FAIL, f"{detail}: imports pause", fix)
    if free < 2 * config.min_free_bytes:
        return Check("Free disk space", Level.WARN, f"{detail}: getting low")
    return Check("Free disk space", Level.OK, detail)


def _writable(probe: SystemProbe, root: Path) -> Check:
    error = probe.writable_error(root)
    if error is None:
        state = "writable" if root.exists() else "will be created on first start"
        return Check("Data folder", Level.OK, f"{root} ({state})")
    return Check("Data folder", Level.FAIL, f"{root}: {error}", "check PA_DATA_ROOT and ownership")


def _database(probe: SystemProbe, root: Path) -> Check:
    database = root / DATABASE_FILE
    if not database.exists():
        return Check("Library database", Level.OK, "none yet (created by the first import)")
    result = probe.database_integrity(database)
    if result == "ok":
        return Check("Library database", Level.OK, "integrity check passed")
    fix = "stop the app and restore the newest file from data/db-backups/ or a backup"
    return Check("Library database", Level.FAIL, result, fix)


def _models(probe: SystemProbe, root: Path) -> Check:
    if probe.has_models(root / "models"):
        return Check("AI models", Level.OK, "found")
    return Check("AI models", Level.OPTIONAL, "none yet: only needed for search and faces (M3)")


def run_doctor(probe: SystemProbe, config: DoctorConfig) -> list[Check]:
    apt = "sudo apt install"
    return [
        _tool(
            "ExifTool",
            probe.tool_version("exiftool"),
            MIN_EXIFTOOL,
            f"{apt} libimage-exiftool-perl",
        ),
        _tool("libvips", probe.libvips_version(), MIN_LIBVIPS, f"{apt} libvips42"),
        _heic(probe, config.heic_sample),
        _disk(probe, config),
        _writable(probe, config.data_root),
        _database(probe, config.data_root),
        _tool(
            "restic (backups)",
            probe.tool_version("restic"),
            MIN_RESTIC,
            f"{apt} restic",
            optional=True,
        ),
        _tool(
            "rclone (remote backups, sources)",
            probe.tool_version("rclone"),
            (1, 50),
            f"{apt} rclone",
            optional=True,
        ),
        _models(probe, config.data_root),
    ]


def render(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        lines.append(f"  [{check.level.value:<4}] {check.name}: {check.detail}")
        if check.fix and check.level is not Level.OK:
            lines.append(f"         fix: {check.fix}")
    failed = sum(c.level is Level.FAIL for c in checks)
    lines.append("")
    lines.append("All required checks passed." if not failed else f"{failed} problem(s) to fix.")
    return "\n".join(lines)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.level is Level.FAIL for c in checks) else 0
