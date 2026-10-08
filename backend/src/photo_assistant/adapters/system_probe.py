"""SystemProbe on this machine: real tools, the real renderer, the real database."""

import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pyvips  # type: ignore[import-untyped]

from photo_assistant.adapters.sqlite_snapshot import open_read_only
from photo_assistant.adapters.tool_runner import ToolMissingError, ToolTimeoutError, run_tool
from photo_assistant.adapters.vips_renderer import VipsRenderer

_VERSION_ARGS = {"exiftool": ["-ver"], "restic": ["version"], "rclone": ["version"]}
_VERSION = re.compile(r"\d+(\.\d+)+")


def _existing(folder: Path) -> Path:
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    return folder


class LocalSystemProbe:
    def tool_version(self, tool: str) -> str | None:
        try:
            done = run_tool([tool, *_VERSION_ARGS.get(tool, ["--version"])], timeout=30)
        except (ToolMissingError, ToolTimeoutError):
            return None
        found = _VERSION.search(done.stdout)
        return found.group(0) if done.returncode == 0 and found else None

    def libvips_version(self) -> str | None:
        return ".".join(str(pyvips.version(n)) for n in range(3))

    def decode_error(self, sample: Path) -> str | None:
        with tempfile.TemporaryDirectory(prefix="pa-doctor-") as scratch:
            try:
                VipsRenderer().render(sample, Path(scratch) / "check.webp", 64)
            except pyvips.Error as exc:
                return str(exc).strip().splitlines()[0] if str(exc).strip() else "decode failed"
        return None

    def free_bytes(self, folder: Path) -> int:
        return shutil.disk_usage(_existing(folder)).free

    def writable_error(self, folder: Path) -> str | None:
        if not folder.exists():
            parent = _existing(folder)
            return None if os.access(parent, os.W_OK) else f"cannot create it inside {parent}"
        try:
            with tempfile.NamedTemporaryFile(dir=folder, prefix=".pa-doctor-"):
                return None
        except OSError as exc:
            return exc.strerror or str(exc)

    def database_integrity(self, database: Path) -> str:
        try:
            conn = open_read_only(database)
        except (OSError, sqlite3.Error) as exc:
            return str(exc)
        try:
            rows = [str(r[0]) for r in conn.execute("PRAGMA integrity_check").fetchmany(5)]
        except sqlite3.DatabaseError as exc:
            return str(exc)
        finally:
            conn.close()
        return "ok" if rows == ["ok"] else "; ".join(rows)

    def has_models(self, folder: Path) -> bool:
        return folder.is_dir() and any(folder.rglob("*.onnx"))
