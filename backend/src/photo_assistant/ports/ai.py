"""The AI socket (FEATURES §7). One port; the app is complete with the Null implementation.

Every AI result is a *proposal* the user accepts or discards; providers never write to the
library. ``plan_album`` returns a plan that already passed ``domain.album_plan.validate``.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from photo_assistant.domain.album_plan import AlbumPlan, LibrarySummary


class Capability(StrEnum):
    CAPTION = "caption"
    PLAN_ALBUM = "plan_album"


class AIUnavailableError(RuntimeError):
    """No provider configured, it can't do what was asked, or it failed twice."""


class AIProvider(Protocol):
    def capabilities(self) -> frozenset[Capability]: ...

    def caption(self, image: bytes, lang: str) -> str:
        """A short, factual description of the photo."""
        ...

    def plan_album(self, prompt: str, context: LibrarySummary) -> AlbumPlan:
        """A validated proposal using only ``context``'s photos and layouts."""
        ...

    def close(self) -> None:
        """Release what the provider holds (a connection); nothing is asked of it after."""
        ...


@dataclass(frozen=True, slots=True)
class AICall:
    """A summary of one request/response. Never contains image bytes."""

    capability: str
    model: str
    request: dict[str, object]
    response: dict[str, object]
    ok: bool
    duration_ms: int
    error: str | None = None
    attempt: int = 1
    extra: dict[str, object] = field(default_factory=dict)


class AILog(Protocol):
    def record(self, call: AICall) -> None: ...
