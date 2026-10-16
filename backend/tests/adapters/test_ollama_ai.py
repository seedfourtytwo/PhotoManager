"""OllamaProvider against a fake Ollama (httpx.MockTransport): no network, no model."""

import base64
import json
from collections.abc import Callable

import httpx
import pytest
import pyvips  # type: ignore[import-untyped]

from photo_assistant.adapters.null_ai import NullAIProvider
from photo_assistant.adapters.ollama_ai import OllamaProvider, OllamaSettings, build_ai_provider
from photo_assistant.domain.album_plan import AlbumPlan, AssetSummary, LibrarySummary, PlanSection
from photo_assistant.ports.ai import AICall, AIUnavailableError, Capability

Handler = Callable[[httpx.Request], httpx.Response]
SETTINGS = OllamaSettings(caption_model="vision:4b", plan_model="planner:8b")
CONTEXT = LibrarySummary(
    assets=(AssetSummary(1, "2019-07-04", "Lyon", ("beach",)), AssetSummary(2, "2019-07-05")),
    layouts=("full", "grid-4"),
)
GOOD_PLAN = {
    "title": "Summer",
    "sections": [
        {
            "title": "Beach",
            "asset_ids": [1, 2],
            "layout_hint": "grid-4",
            "captions": [{"asset_id": 1, "text": "Waves"}],
        }
    ],
}


class ListLog:
    def __init__(self) -> None:
        self.calls: list[AICall] = []

    def record(self, call: AICall) -> None:
        self.calls.append(call)


def _chat_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"model": "m", "message": {"role": "assistant", "content": content}}
    )


class FakeOllama:
    """Routes like Ollama; ``chat_replies`` are served in order; records every request."""

    def __init__(self, chat_replies: list[str | Exception] | None = None) -> None:
        self.chat_replies = list(chat_replies or [])
        self.requests: list[httpx.Request] = []
        self.tags = ["vision:4b", "planner:8b"]
        self.show: dict[str, list[str] | None] = {"vision:4b": ["completion", "vision"]}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in self.tags]})
        if request.url.path == "/api/show":
            caps = self.show.get(json.loads(request.content)["model"])
            return httpx.Response(200, json={} if caps is None else {"capabilities": caps})
        reply = self.chat_replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _chat_reply(reply)

    def chat_bodies(self) -> list[dict[str, object]]:
        return [json.loads(r.content) for r in self.requests if r.url.path == "/api/chat"]


def _provider(
    fake: Handler, settings: OllamaSettings = SETTINGS, log: ListLog | None = None
) -> tuple[OllamaProvider, ListLog]:
    log = log or ListLog()
    client = httpx.Client(transport=httpx.MockTransport(fake), base_url=settings.base_url)
    return OllamaProvider(settings, log, client=client), log


def _synthetic_jpeg(width: int = 3000, height: int = 2000) -> bytes:
    image = pyvips.Image.black(width, height, bands=3).linear([1, 1, 1], [40, 120, 200])
    data: bytes = image.cast("uchar").jpegsave_buffer(Q=80)
    return data


# --- capabilities ----------------------------------------------------------------------------


def test_capabilities_come_from_the_models_the_server_has() -> None:
    fake = FakeOllama()
    provider, _ = _provider(fake)
    assert provider.capabilities() == {Capability.CAPTION, Capability.PLAN_ALBUM}
    provider.capabilities()  # cached: asked once
    assert [r.url.path for r in fake.requests] == ["/api/tags", "/api/show"]


def test_a_caption_model_without_vision_offers_no_captions() -> None:
    fake = FakeOllama()
    fake.show["vision:4b"] = ["completion"]
    provider, _ = _provider(fake)
    assert provider.capabilities() == {Capability.PLAN_ALBUM}


def test_older_servers_without_capability_info_trust_the_configured_model() -> None:
    fake = FakeOllama()
    fake.show["vision:4b"] = None
    provider, _ = _provider(fake)
    assert Capability.CAPTION in provider.capabilities()


def test_models_not_pulled_are_not_offered() -> None:
    fake = FakeOllama()
    fake.tags = ["planner:8b"]
    provider, _ = _provider(fake)
    assert provider.capabilities() == {Capability.PLAN_ALBUM}


def test_model_names_match_with_or_without_the_latest_tag() -> None:
    fake = FakeOllama()
    fake.tags = ["planner:latest"]
    provider, _ = _provider(fake, OllamaSettings(plan_model="planner"))
    assert provider.capabilities() == {Capability.PLAN_ALBUM}


def test_an_unreachable_server_offers_nothing_and_is_asked_again_later() -> None:
    calls = []

    def down(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("connection refused")

    provider, _ = _provider(down)
    assert provider.capabilities() == frozenset()
    assert provider.capabilities() == frozenset()
    assert len(calls) == 2


def test_no_models_configured_means_no_calls_at_all() -> None:
    fake = FakeOllama()
    provider, _ = _provider(fake, OllamaSettings())
    assert provider.capabilities() == frozenset()
    with pytest.raises(AIUnavailableError, match="no model"):
        provider.caption(_synthetic_jpeg(), "en")
    with pytest.raises(AIUnavailableError, match="no model"):
        provider.plan_album("summer", CONTEXT)
    assert fake.requests == []


def test_build_ai_provider_defaults_to_null() -> None:
    assert isinstance(build_ai_provider(None, ListLog()), NullAIProvider)
    assert isinstance(build_ai_provider(SETTINGS, ListLog()), OllamaProvider)


# --- caption ---------------------------------------------------------------------------------


def test_caption_sends_a_downscaled_image_and_returns_the_text() -> None:
    fake = FakeOllama([json.dumps({"caption": "  A blue sky.  "})])
    provider, _ = _provider(fake)
    assert provider.caption(_synthetic_jpeg(), "fr") == "A blue sky."
    (body,) = fake.chat_bodies()
    assert body["model"] == "vision:4b"
    assert body["stream"] is False
    assert isinstance(body["format"], dict)
    user = body["messages"][-1]  # type: ignore[index]
    assert "fr" in user["content"]
    sent = pyvips.Image.new_from_buffer(base64.b64decode(user["images"][0]), "")
    assert max(sent.width, sent.height) == SETTINGS.image_max_edge


def test_every_chat_turns_thinking_off() -> None:
    # qwen3/qwen3.5 think before answering unless told not to: one album took over 10 minutes
    fake = FakeOllama([json.dumps({"caption": "A blue sky."}), json.dumps(GOOD_PLAN)])
    provider, _ = _provider(fake)
    provider.caption(_synthetic_jpeg(200, 100), "en")
    provider.plan_album("summer", CONTEXT)
    assert [body["think"] for body in fake.chat_bodies()] == [False, False]


def test_caption_logs_a_summary_without_image_bytes() -> None:
    image = _synthetic_jpeg()
    fake = FakeOllama([json.dumps({"caption": "A blue sky."})])
    provider, log = _provider(fake)
    provider.caption(image, "en")
    (call,) = log.calls
    assert (call.capability, call.model, call.ok, call.attempt) == ("caption", "vision:4b", True, 1)
    logged = json.dumps([call.request, call.response])
    sent_b64 = fake.chat_bodies()[0]["messages"][-1]["images"][0]  # type: ignore[index]
    assert sent_b64[:200] not in logged
    assert call.request["images"] == [{"bytes": len(base64.b64decode(sent_b64))}]
    assert call.response["content"] == json.dumps({"caption": "A blue sky."})


def test_invalid_caption_json_is_retried_once() -> None:
    fake = FakeOllama(["not json", json.dumps({"caption": "Two dogs."})])
    provider, log = _provider(fake)
    assert provider.caption(_synthetic_jpeg(200, 100), "en") == "Two dogs."
    assert [c.ok for c in log.calls] == [False, True]
    assert log.calls[0].error is not None


def test_captions_failing_twice_raise_a_clear_error() -> None:
    fake = FakeOllama([json.dumps({"caption": ""}), json.dumps({"caption": "x" * 500})])
    provider, log = _provider(fake)
    with pytest.raises(AIUnavailableError, match="not usable"):
        provider.caption(_synthetic_jpeg(200, 100), "en")
    assert len(log.calls) == 2


def test_a_file_that_is_not_an_image_is_not_sent() -> None:
    fake = FakeOllama()
    provider, _ = _provider(fake)
    with pytest.raises(AIUnavailableError, match="could not read"):
        provider.caption(b"definitely not a jpeg", "en")
    assert fake.chat_bodies() == []


# --- plan_album ------------------------------------------------------------------------------


def test_plan_album_returns_a_validated_plan() -> None:
    fake = FakeOllama([json.dumps(GOOD_PLAN)])
    provider, log = _provider(fake)
    plan = provider.plan_album("our summer", CONTEXT)
    assert plan == AlbumPlan("Summer", (PlanSection("Beach", (1, 2), "grid-4", {1: "Waves"}),))
    (body,) = fake.chat_bodies()
    assert body["model"] == "planner:8b"
    schema = body["format"]
    assert schema["properties"]["sections"]["items"]["properties"]["layout_hint"]["enum"] == [  # type: ignore[index]
        "full",
        "grid-4",
    ]
    assert "1|2019-07-04|Lyon|beach" in body["messages"][-1]["content"]  # type: ignore[index]
    assert log.calls[0].capability == "plan_album"
    assert log.calls[0].request["photos"] == 2


def test_a_plan_with_unknown_photos_is_retried_with_the_problems_then_accepted() -> None:
    bad = {**GOOD_PLAN, "sections": [{**GOOD_PLAN["sections"][0], "asset_ids": [1, 99]}]}  # type: ignore[dict-item]
    fake = FakeOllama([json.dumps(bad), json.dumps(GOOD_PLAN)])
    provider, log = _provider(fake)
    assert provider.plan_album("summer", CONTEXT).title == "Summer"
    retry = fake.chat_bodies()[1]["messages"]
    assert "unknown photo id 99" in retry[-1]["content"]  # type: ignore[index]
    assert retry[-2]["role"] == "assistant"  # type: ignore[index]
    assert [c.ok for c in log.calls] == [False, True]
    assert "unknown photo id 99" in (log.calls[0].error or "")


def test_schema_violating_plans_are_rejected_after_one_retry() -> None:
    fake = FakeOllama([json.dumps({"title": "x"}), json.dumps({"sections": "nope"})])
    provider, _ = _provider(fake)
    with pytest.raises(AIUnavailableError, match="not usable"):
        provider.plan_album("summer", CONTEXT)
    assert len(fake.chat_bodies()) == 2


def test_timeouts_are_not_retried_and_say_so() -> None:
    fake = FakeOllama([httpx.ReadTimeout("slow")])
    provider, log = _provider(fake)
    with pytest.raises(AIUnavailableError, match="did not answer in time"):
        provider.plan_album("summer", CONTEXT)
    assert len(log.calls) == 1
    assert not log.calls[0].ok


def test_http_errors_become_ai_unavailable() -> None:
    def missing_model(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'planner:8b' not found"})

    provider, log = _provider(missing_model)
    with pytest.raises(AIUnavailableError, match="not found"):
        provider.plan_album("summer", CONTEXT)
    assert log.calls[0].response["status"] == 404


def test_connection_errors_become_ai_unavailable() -> None:
    fake = FakeOllama([httpx.ConnectError("refused")])
    provider, _ = _provider(fake)
    with pytest.raises(AIUnavailableError, match="cannot reach"):
        provider.plan_album("summer", CONTEXT)


def test_a_malformed_ollama_envelope_counts_as_invalid_output() -> None:
    replies = iter([httpx.Response(200, json={"oops": 1}), _chat_reply(json.dumps(GOOD_PLAN))])
    provider, log = _provider(lambda r: next(replies))
    assert provider.plan_album("summer", CONTEXT).title == "Summer"
    assert [c.ok for c in log.calls] == [False, True]


def test_the_null_provider_cannot_plan_either() -> None:
    with pytest.raises(AIUnavailableError, match="no AI configured"):
        NullAIProvider().plan_album("summer", CONTEXT)
