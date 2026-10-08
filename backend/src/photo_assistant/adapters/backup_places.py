"""BackupPlaces on this machine: mounted external disks, rclone remotes, facts about a place.

Nothing here creates or changes a backup location; the write check makes and removes one
temporary file in the folder the backup would go into.
"""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from photo_assistant.domain.backup import PlaceFacts, TargetKind, target_kind
from photo_assistant.ports.backup import Disk

DISK_ROOTS = (Path("/media"), Path("/run/media"), Path("/mnt"))
RESTIC_MARKER = "config"  # every restic repository has this file at its top
_RCLONE_TIMEOUT = 30.0


def _unescape(mount_point: str) -> str:
    """/proc/mounts writes a space as \\040 (and tab, newline, backslash the same way)."""
    for code in ("040", "011", "012", "134"):
        mount_point = mount_point.replace(f"\\{code}", chr(int(code, 8)))
    return mount_point


class LocalBackupPlaces:
    def __init__(
        self,
        rclone_binary: str = "rclone",
        rclone_config: Path | None = None,
        mounts_file: Path = Path("/proc/mounts"),
        disk_roots: Sequence[Path] = DISK_ROOTS,
    ) -> None:
        self._rclone = rclone_binary
        self._rclone_config = rclone_config
        self._mounts_file = mounts_file
        self._disk_roots = tuple(disk_roots)

    def disks(self) -> list[Disk]:
        try:
            lines = self._mounts_file.read_text().splitlines()
        except OSError:
            return []
        found = []
        for line in lines:
            fields = line.split()
            if len(fields) < 2:
                continue
            mount = Path(_unescape(fields[1]))
            if not any(root in mount.parents for root in self._disk_roots):
                continue
            try:
                free = shutil.disk_usage(mount).free
            except OSError:  # listed but not reachable (unplugged without unmounting)
                continue
            found.append(Disk(str(mount), mount.name, free))
        return sorted(found, key=lambda d: d.label.casefold())

    def remotes(self) -> list[str]:
        listed = self._rclone_output(["listremotes"])
        if listed is None:
            return []
        return sorted(line.rstrip(":") for line in listed.splitlines() if line.strip())

    def facts(self, repository: str, data_root: Path) -> PlaceFacts:
        if target_kind(repository) is TargetKind.RCLONE:
            return PlaceFacts(free_bytes=self._remote_free(repository))
        return self._local_facts(Path(repository), data_root)

    def _local_facts(self, repository: Path, data_root: Path) -> PlaceFacts:
        place = repository.parent
        if not place.is_dir():
            return PlaceFacts(None, write_error=f"{place} does not exist: is the disk plugged in?")
        if repository.exists() and not repository.is_dir():
            return PlaceFacts(None, write_error=f"{repository} is there and is not a folder")
        try:
            with tempfile.NamedTemporaryFile(dir=place, prefix=".pa-backup-check-"):
                pass
            free = shutil.disk_usage(place).free
            same_disk = place.stat().st_dev == data_root.stat().st_dev
        except OSError as exc:
            return PlaceFacts(None, write_error=exc.strerror or str(exc))
        holds_backup = (repository / RESTIC_MARKER).is_file()
        return PlaceFacts(free, same_disk=same_disk, holds_backup=holds_backup)

    def _remote_free(self, repository: str) -> int | None:
        remote = repository.removeprefix("rclone:").partition(":")[0]
        answer = self._rclone_output(["about", f"{remote}:", "--json"])
        try:
            free = json.loads(answer or "")["free"]
        except (ValueError, KeyError, TypeError):
            return None
        return free if isinstance(free, int) and free >= 0 else None

    def _rclone_output(self, args: list[str]) -> str | None:
        """rclone's answer, or None when it is missing, slow or refuses."""
        command = [self._rclone, *args]
        if self._rclone_config is not None:
            command += ["--config", str(self._rclone_config)]
        try:
            done = subprocess.run(  # an argument list, never a shell
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_RCLONE_TIMEOUT,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout if done.returncode == 0 else None
