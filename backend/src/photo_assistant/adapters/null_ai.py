from photo_assistant.domain.album_plan import AlbumPlan, LibrarySummary
from photo_assistant.ports.ai import AIUnavailableError, Capability

_NOT_CONFIGURED = "no AI configured (set one up in settings, M5)"


class NullAIProvider:
    """Default provider: offers nothing, so the UI hides every AI affordance."""

    def capabilities(self) -> frozenset[Capability]:
        return frozenset()

    def caption(self, image: bytes, lang: str) -> str:
        raise AIUnavailableError(_NOT_CONFIGURED)

    def plan_album(self, prompt: str, context: LibrarySummary) -> AlbumPlan:
        raise AIUnavailableError(_NOT_CONFIGURED)
