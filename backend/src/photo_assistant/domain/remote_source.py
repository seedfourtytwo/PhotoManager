"""Configuration of a remote source: *which* place to read, never *how to log in*.

rclone remotes: credentials live in rclone's own (encrypted) config file. The library database
only stores the remote's name and a path on it, so only plain named remotes are accepted:
rclone's on-the-fly ``:backend,key=value:`` syntax could smuggle secrets into our database.

Proton Drive: the sign-in lives in Proton's own CLI (system keyring); we store only which part
of the Drive to read — the Photos section, or a folder under "My files".
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

# rclone: letters, digits, _ - . + @ and space; not starting with - or space.
_REMOTE_NAME = re.compile(r"^[\w.+@][\w.+@ -]{0,63}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_PATH_CHARS = 1024

RCLONE = "rclone"
PROTON = "proton"
PROTON_PHOTOS = "/photos"
PROTON_FILES = "/my-files"


class RemoteConfigError(ValueError):
    """The remote source settings are not usable; the message says what to fix."""


@dataclass(frozen=True, slots=True)
class RemoteConfig:
    remote: str
    path: str = ""
    provider: str = RCLONE

    @property
    def target(self) -> str:
        """What rclone reads from: ``remote:path``."""
        return f"{self.remote}:{self.path}"

    @property
    def place(self) -> str:
        """What the user chose, for showing next to the source."""
        return self.path if self.provider == PROTON else self.target

    def to_mapping(self) -> dict[str, str]:
        if self.provider == PROTON:
            return {"provider": PROTON, "path": self.path}
        return {"remote": self.remote, "path": self.path}

    @classmethod
    def proton(cls, path: str) -> "RemoteConfig":
        """The Photos section (``/photos``) or a place in My files (``/my-files[/...]``)."""
        in_files = path == PROTON_FILES or path.startswith(PROTON_FILES + "/")
        parts = path.split("/")[1:]
        if (
            (path != PROTON_PHOTOS and not in_files)
            or any(part in ("", ".", "..") for part in parts)
            or _CONTROL.search(path)
            or len(path) > MAX_PATH_CHARS
        ):
            raise RemoteConfigError(
                f"choose the Photos section ({PROTON_PHOTOS}) or a folder in My files "
                f"({PROTON_FILES}/...)"
            )
        return cls(PROTON, path, PROTON)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "RemoteConfig":
        provider = data.get("provider", RCLONE)
        if provider == PROTON:
            path = data.get("path")
            return cls.proton(path if isinstance(path, str) else "")
        if provider != RCLONE:
            raise RemoteConfigError(f"unknown provider '{provider}'")
        remote = data.get("remote")
        path = data.get("path", "")
        if not isinstance(remote, str) or not _REMOTE_NAME.fullmatch(remote):
            raise RemoteConfigError(
                "remote must be the name of a remote set up with 'rclone config' "
                "(letters, digits, spaces, . _ - + @)"
            )
        if not isinstance(path, str) or _CONTROL.search(path) or len(path) > MAX_PATH_CHARS:
            raise RemoteConfigError("path must be plain text without line breaks")
        return cls(remote, path)


def proton_folder_name_problem(name: str) -> str | None:
    """Why a new Proton Drive folder can't be called ``name``, or None."""
    if not name.strip() or name in (".", ".."):
        return "give the new folder a name"
    if "/" in name or "\\" in name or _CONTROL.search(name):
        return "a folder name can't contain / or \\ or line breaks"
    if name.startswith("-") or name != name.strip():
        return "a folder name can't start with - or start or end with a space"
    if len(name) > 255:
        return "that name is too long"
    return None
