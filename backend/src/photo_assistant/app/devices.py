"""Device tokens for non-browser clients (Apple Shortcuts now, a phone app later).

A token is shown once, at creation. Only its SHA-256 is stored: tokens are 256 random bits, so
a slow password hash adds nothing, and a leaked database cannot be used to upload.
"""

import hashlib
import re
import secrets

from photo_assistant.ports import Clock
from photo_assistant.ports.upload import Device, DeviceStore

TOKEN_PREFIX = "pa_dev_"  # recognisable in logs and secret scanners
PLATFORMS = frozenset({"ios", "android", "desktop", "other"})
MAX_NAME_CHARS = 60
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceTokens:
    def __init__(self, store: DeviceStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def create(self, user_id: int, name: str, platform: str = "other") -> tuple[Device, str]:
        """The new device and its token (the only time the token is ever available)."""
        clean = _CONTROL.sub("", name).strip()
        if not clean or len(clean) > MAX_NAME_CHARS:
            raise ValueError(f"give the device a name of 1 to {MAX_NAME_CHARS} characters")
        if platform not in PLATFORMS:
            raise ValueError(f"platform must be one of: {', '.join(sorted(PLATFORMS))}")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        device = self._store.add_device(
            user_id, clean, platform, hash_token(token), self._clock.now()
        )
        return device, token

    def list(self, user_id: int) -> list[Device]:
        return self._store.list_devices(user_id)

    def revoke(self, user_id: int, device_id: int) -> bool:
        return self._store.revoke_device(user_id, device_id, self._clock.now())

    def authenticate(self, token: str) -> int | None:
        """The user a valid, unrevoked token belongs to."""
        if not token.startswith(TOKEN_PREFIX):
            return None
        return self._store.user_for_token_hash(hash_token(token), self._clock.now())
