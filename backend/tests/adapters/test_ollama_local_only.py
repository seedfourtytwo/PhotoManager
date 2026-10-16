"""The AI stays home: Ollama only on this machine or the private network, no cloud models,
no redirects. Against a fake Ollama (httpx.MockTransport) and a fake resolver: no network."""

import json
import logging

import httpx
import pytest

from photo_assistant.adapters.ollama_ai import OllamaProvider, OllamaSettings
from photo_assistant.adapters.ollama_guard import (
    NotLocalError,
    Resolve,
    check_host,
    is_cloud_model,
    is_local_address,
)
from photo_assistant.ports.ai import AIUnavailableError, AIUnreachableError, Capability
from tests.adapters.test_ollama_ai import CONTEXT, GOOD_PLAN, FakeOllama, ListLog


def test_a_refusal_is_about_the_server_not_the_photo() -> None:
    """Background jobs give up on a photo or album only for an unusable answer; a server they
    may not use is the server's fault, so the job is retried and no photo is marked failed."""
    assert issubclass(NotLocalError, AIUnreachableError)

PUBLIC_IP = "34.36.133.15"


def _resolver(table: dict[str, list[str]]) -> Resolve:
    def resolve(host: str) -> list[str]:
        if host not in table:
            raise OSError(f"cannot resolve {host}")
        return table[host]

    return resolve


def _provider(
    fake: FakeOllama,
    settings: OllamaSettings,
    resolve: dict[str, list[str]] | None = None,
) -> tuple[OllamaProvider, ListLog]:
    log = ListLog()
    provider = OllamaProvider(
        settings, log, transport=httpx.MockTransport(fake), resolve=_resolver(resolve or {})
    )
    return provider, log


# --- addresses -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.5",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.1.20",
        "100.64.0.1",  # Tailscale (CGNAT range)
        "100.127.255.254",
        "fd7a:115c:a1e0::1",  # Tailscale IPv6
        "::ffff:192.168.1.20",
    ],
)
def test_loopback_private_and_tailscale_addresses_are_local(ip: str) -> None:
    assert is_local_address(ip)


@pytest.mark.parametrize(
    "ip",
    [
        PUBLIC_IP,
        "8.8.8.8",
        "172.32.0.1",
        "192.169.0.1",
        "100.128.0.1",
        "169.254.1.1",
        "0.0.0.0",
        "2001:4860:4860::8888",
        "fd00::1",  # a private IPv6 range, but not Tailscale's
        "::ffff:8.8.8.8",
        "not-an-ip",
    ],
)
def test_public_and_other_addresses_are_not_local(ip: str) -> None:
    assert not is_local_address(ip)


def test_a_name_is_judged_by_every_address_it_resolves_to() -> None:
    resolve = _resolver(
        {
            "localhost": ["127.0.0.1", "::1"],
            "homeserver.tail1234.ts.net": ["100.101.102.103"],
            "ollama.com": [PUBLIC_IP],
            "split.example": ["192.168.1.2", PUBLIC_IP],
        }
    )
    check_host("localhost", resolve)
    check_host("homeserver.tail1234.ts.net", resolve)
    with pytest.raises(NotLocalError, match=PUBLIC_IP):
        check_host("ollama.com", resolve)
    with pytest.raises(NotLocalError, match=PUBLIC_IP):
        check_host("split.example", resolve)


def test_an_ip_literal_is_not_resolved() -> None:
    check_host("192.168.1.2", _resolver({}))
    with pytest.raises(NotLocalError):
        check_host("8.8.8.8", _resolver({}))


@pytest.mark.parametrize(
    "url",
    [
        f"http://{PUBLIC_IP}:11434",
        "http://ollama.com:11434",
        "https://ollama.com",
        "http://[2001:4860:4860::8888]:11434",
        "ftp://127.0.0.1:11434",
        "http://:11434",
    ],
)
def test_a_base_url_off_this_machine_and_network_stops_the_start(url: str) -> None:
    with pytest.raises(NotLocalError, match="PA_OLLAMA_BASE_URL"):
        _provider(FakeOllama(), OllamaSettings(base_url=url), {"ollama.com": [PUBLIC_IP]})


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
        "http://192.168.1.20:11434",
        "http://100.101.102.103:11434",
        "http://homeserver.tail1234.ts.net:11434",
    ],
)
def test_a_base_url_on_this_machine_or_network_is_accepted(url: str) -> None:
    resolve = {"localhost": ["127.0.0.1"], "homeserver.tail1234.ts.net": ["100.101.102.103"]}
    _provider(FakeOllama(), OllamaSettings(base_url=url), resolve)


def test_a_name_that_does_not_resolve_yet_is_checked_again_on_every_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The home server may be off at start (Tailscale down): the app starts, the AI waits."""
    table: dict[str, list[str]] = {}
    fake = FakeOllama([json.dumps(GOOD_PLAN)])
    log = ListLog()
    settings = OllamaSettings(base_url="http://homeserver:11434", plan_model="planner:8b")
    with caplog.at_level(logging.WARNING):
        provider = OllamaProvider(
            settings, log, transport=httpx.MockTransport(fake), resolve=_resolver(table)
        )
    assert "homeserver" in caplog.text

    assert provider.capabilities() == frozenset()  # still unresolvable: unreachable
    table["homeserver"] = [PUBLIC_IP]  # now it points off the network
    assert provider.capabilities() == frozenset()
    with pytest.raises(NotLocalError, match=PUBLIC_IP):
        provider.plan_album("summer", CONTEXT)
    assert fake.requests == []
    assert [c.ok for c in log.calls] == [False]

    table["homeserver"] = ["100.101.102.103"]
    assert provider.capabilities() == {Capability.PLAN_ALBUM}


# --- cloud models ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["gpt-oss:120b-cloud", "gpt-oss:cloud", "gpt-oss:20b:cloud", "Qwen3-Coder:480B-Cloud"],
)
def test_cloud_tagged_model_names_are_cloud_models(name: str) -> None:
    assert is_cloud_model(name)


@pytest.mark.parametrize(
    "name",
    ["qwen3:8b", "llava", "cloudy:7b", "my-cloud-model", "qwen3:8b:local", "host:5000/cloud"],
)
def test_other_model_names_are_not_cloud_models(name: str) -> None:
    assert not is_cloud_model(name)


@pytest.mark.parametrize(
    ("settings", "which"),
    [
        (OllamaSettings(plan_model="gpt-oss:120b-cloud"), "plan model"),
        (OllamaSettings(caption_model="qwen3-vl:cloud"), "caption model"),
    ],
)
def test_a_configured_cloud_model_stops_the_start(settings: OllamaSettings, which: str) -> None:
    with pytest.raises(NotLocalError, match=which):
        _provider(FakeOllama(), settings)


def test_a_model_the_server_lists_as_remote_is_not_offered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A local alias of a cloud model (``FROM gpt-oss:120b-cloud``) has a plain name; Ollama
    marks it with ``remote_host`` in /api/tags."""
    fake = FakeOllama()
    fake.remote = {"planner:8b": "https://ollama.com:443"}
    provider, _ = _provider(fake, OllamaSettings(plan_model="planner:8b"))
    with caplog.at_level(logging.WARNING):
        assert provider.capabilities() == frozenset()
    assert "planner:8b" in caplog.text and "ollama.com" in caplog.text
    with pytest.raises(NotLocalError, match="cloud"):
        provider.plan_album("summer", CONTEXT)
    assert fake.chat_bodies() == []


def test_a_caption_model_shown_as_remote_is_not_offered() -> None:
    fake = FakeOllama()
    fake.show_remote = {"vision:4b": "https://ollama.com:443"}
    provider, _ = _provider(fake, OllamaSettings(caption_model="vision:4b"))
    assert provider.capabilities() == frozenset()


def test_an_answer_that_came_from_a_remote_host_is_refused_and_not_retried() -> None:
    fake = FakeOllama()
    provider, log = _provider(fake, OllamaSettings(plan_model="planner:8b"))
    fake.chat_replies = [json.dumps(GOOD_PLAN), json.dumps(GOOD_PLAN)]
    fake.chat_remote_host = "https://ollama.com:443"
    with pytest.raises(NotLocalError, match="cloud"):
        provider.plan_album("summer", CONTEXT)
    assert len(fake.chat_bodies()) == 1
    assert [c.ok for c in log.calls] == [False]
    with pytest.raises(NotLocalError, match="cloud"):  # and that model stays refused
        provider.plan_album("summer", CONTEXT)
    assert len(fake.chat_bodies()) == 1


# --- redirects -------------------------------------------------------------------------------


def _redirecting(paths: set[str]) -> FakeOllama:
    fake = FakeOllama([json.dumps(GOOD_PLAN)])
    fake.redirect = {p: "https://ollama.com/api/chat" for p in paths}
    return fake


def test_a_redirected_chat_is_not_followed() -> None:
    fake = _redirecting({"/api/chat"})
    provider, log = _provider(fake, OllamaSettings(plan_model="planner:8b"))
    with pytest.raises(NotLocalError, match="redirect"):
        provider.plan_album("summer", CONTEXT)
    assert [r.url.host for r in fake.requests] == ["127.0.0.1"]
    assert log.calls[0].response["status"] == 307


def test_a_redirected_model_list_offers_nothing() -> None:
    fake = _redirecting({"/api/tags"})
    provider, _ = _provider(fake, OllamaSettings(plan_model="planner:8b"))
    assert provider.capabilities() == frozenset()
    assert [r.url.host for r in fake.requests] == ["127.0.0.1"]
