"""Closing the services releases what they hold, whichever AI provider is configured."""

from pathlib import Path

from photo_assistant.adapters.null_ai import NullAIProvider
from photo_assistant.adapters.ollama_ai import OllamaProvider
from photo_assistant.api.services import build_services
from tests.api.conftest import make_settings


def test_closing_the_services_closes_the_ollama_client(tmp_path: Path) -> None:
    ollama = {"ai_provider": "ollama", "ollama_plan_model": "p"}
    services = build_services(make_settings(tmp_path / "data", integrations=ollama))
    ai = services.integrations.ai
    assert isinstance(ai, OllamaProvider)
    services.close()
    assert ai._client.is_closed


def test_closing_the_services_without_ai_is_fine(tmp_path: Path) -> None:
    services = build_services(make_settings(tmp_path / "data"))
    assert isinstance(services.integrations.ai, NullAIProvider)
    services.close()
