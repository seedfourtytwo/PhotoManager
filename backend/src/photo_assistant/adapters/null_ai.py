from photo_assistant.ports.ai import AIUnavailableError, Capability


class NullAIProvider:
    """Default provider: offers nothing, so the UI hides every AI affordance."""

    def capabilities(self) -> frozenset[Capability]:
        return frozenset()

    def caption(self, image: bytes, lang: str) -> str:
        raise AIUnavailableError("no AI configured (set one up in settings, M5)")
