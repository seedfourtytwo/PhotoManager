import pytest

from photo_assistant.adapters.null_ai import NullAIProvider
from photo_assistant.ports.ai import AIProvider, AIUnavailableError, Capability


def test_null_provider_offers_nothing_and_says_so() -> None:
    provider: AIProvider = NullAIProvider()
    assert provider.capabilities() == frozenset()
    with pytest.raises(AIUnavailableError, match="no AI configured"):
        provider.caption(b"jpeg bytes", lang="en")


def test_capabilities_cover_the_planned_features() -> None:
    assert {c.value for c in Capability} == {"caption", "plan_album"}
