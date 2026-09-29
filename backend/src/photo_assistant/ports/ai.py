"""The AI socket (FEATURES §7). One port; the app is complete with the Null implementation.

Every AI result is a *proposal* the user accepts or discards; providers never write to the
library. More capabilities (album planning) arrive with their features in M5.
"""

from enum import StrEnum
from typing import Protocol


class Capability(StrEnum):
    CAPTION = "caption"
    PLAN_ALBUM = "plan_album"


class AIUnavailableError(RuntimeError):
    """No provider configured, or it can't do what was asked."""


class AIProvider(Protocol):
    def capabilities(self) -> frozenset[Capability]: ...

    def caption(self, image: bytes, lang: str) -> str:
        """A short, factual description of the photo."""
        ...
