"""Configuration of a remote (rclone) source: *which* remote, never *how to log in*.

Credentials live in rclone's own (encrypted) config file. The library database only stores
the remote's name and a path on it, so only plain named remotes are accepted: rclone's
on-the-fly ``:backend,key=value:`` syntax could smuggle secrets into our database.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

# rclone: letters, digits, _ - . + @ and space; not starting with - or space.
_REMOTE_NAME = re.compile(r"^[\w.+@][\w.+@ -]{0,63}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_PATH_CHARS = 1024


class RemoteConfigError(ValueError):
    """The remote source settings are not usable; the message says what to fix."""


@dataclass(frozen=True, slots=True)
class RemoteConfig:
    remote: str
    path: str = ""

    @property
    def target(self) -> str:
        """What rclone reads from: ``remote:path``."""
        return f"{self.remote}:{self.path}"

    def to_mapping(self) -> dict[str, str]:
        return {"remote": self.remote, "path": self.path}

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "RemoteConfig":
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
