"""AIProvider backed by an Ollama server (laptop or home server over Tailscale).

- Only the configured base URL is ever called, and only when a model is configured. It must be
  on this machine or the private network, its models local, and redirects are never followed
  (``ollama_guard``): checked at start and again on every request.
- Images are downscaled and stripped of metadata (GPS!) before they leave this process.
- Output is constrained by a JSON schema (Ollama's ``format``), parsed strictly, validated by
  domain rules; one retry (with the problems fed back), then AIUnavailableError.
- Every chat request/response is summarised in the AI log; image bytes are never logged.
"""

import base64
import json
import logging
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import TypeVar

import httpx
import pyvips  # type: ignore[import-untyped]

from photo_assistant.adapters.null_ai import NullAIProvider
from photo_assistant.adapters.ollama_guard import (
    NotLocalError,
    Resolve,
    check_host,
    is_cloud_model,
    system_resolve,
)
from photo_assistant.domain.album_plan import (
    AlbumPlan,
    LibrarySummary,
    PlanFormatError,
    plan_from_json,
    summary_lines,
    validate,
)
from photo_assistant.ports.ai import (
    AICall,
    AILog,
    AIProvider,
    AIUnavailableError,
    AIUnreachableError,
    Capability,
)

log = logging.getLogger(__name__)
T = TypeVar("T")
Downscale = Callable[[bytes, int], bytes]
_LOGGED_TEXT = 4000  # characters of prompt/response kept in the log


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    base_url: str = "http://127.0.0.1:11434"
    caption_model: str | None = None  # a vision model, e.g. a small Gemma or Qwen-VL
    plan_model: str | None = None
    timeout_seconds: float = 120.0  # local models on an 8 GB GPU are slow
    connect_timeout_seconds: float = 5.0
    image_max_edge: int = 1024
    max_caption_chars: int = 200


class _BadOutputError(ValueError):
    """The model answered, but not with something usable (worth one retry)."""


def jpeg_preview(image: bytes, max_edge: int) -> bytes:
    """A small, orientation-corrected JPEG without any metadata."""
    try:
        thumb = pyvips.Image.thumbnail_buffer(image, max_edge, height=max_edge, size="down")
        if thumb.interpretation not in ("srgb", "b-w"):
            thumb = thumb.colourspace("srgb")
        data: bytes = thumb.jpegsave_buffer(Q=85, strip=True)
    except pyvips.Error as exc:
        raise AIUnavailableError("could not read the photo to describe it") from exc
    return data


def build_ai_provider(settings: OllamaSettings | None, log: AILog) -> AIProvider:
    """The Null provider unless Ollama is explicitly configured."""
    if settings is None:
        return NullAIProvider()
    return OllamaProvider(settings, log)


_CAPTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"caption": {"type": "string"}},
    "required": ["caption"],
}
_CAPTION_SYSTEM = (
    "You describe family photos for a private photo library. Reply with one short, factual "
    "sentence: what is visible. Do not guess names, ages or places."
)
_PLAN_SYSTEM = (
    "You arrange the photos of one event into an album. Use every photo id from the list you "
    "are given exactly once, and no other. Group them in time order into sections with a short "
    "title; give each section a layout_hint from the allowed values whose photos per page "
    "divides the section's photo count. Optionally add short captions. Describe only what the "
    "photo descriptions and places say; do not guess names. Answer with JSON only."
)


def _plan_schema(layouts: Collection[str], max_caption: int) -> dict[str, object]:
    caption = {
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer"},
            "text": {"type": "string", "maxLength": max_caption},
        },
        "required": ["asset_id", "text"],
    }
    section = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "asset_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
            "layout_hint": {"type": "string", "enum": list(layouts)},
            "captions": {"type": "array", "items": caption},
        },
        "required": ["title", "asset_ids", "layout_hint"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "sections": {"type": "array", "items": section, "minItems": 1},
        },
        "required": ["title", "sections"],
    }


def _layout_list(layouts: Mapping[str, int]) -> str:
    def per_page(n: int) -> str:
        return f"{n} photo a page" if n == 1 else f"{n} photos a page"

    return ", ".join(f"{name} ({per_page(n)})" for name, n in layouts.items())


def _same_model(wanted: str, available: str) -> bool:
    """``llava`` and ``llava:latest`` are the same model to Ollama."""

    def full(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return full(wanted) == full(available)


class OllamaProvider:
    def __init__(
        self,
        settings: OllamaSettings,
        log: AILog,
        *,
        transport: httpx.BaseTransport | None = None,
        downscale: Downscale = jpeg_preview,
        resolve: Resolve = system_resolve,
    ) -> None:
        _refuse_cloud_models(settings)
        _check_base_url(settings.base_url, resolve)
        self._settings = settings
        self._log = log
        self._downscale = downscale
        self._resolve = resolve
        self._client = httpx.Client(
            base_url=settings.base_url,
            timeout=httpx.Timeout(
                settings.timeout_seconds, connect=settings.connect_timeout_seconds
            ),
            follow_redirects=False,  # a redirect could lead anywhere
            event_hooks={"request": [self._check_request]},
            transport=transport,
        )
        self._capabilities: frozenset[Capability] | None = None
        self._remote: set[str] = set()  # models Ollama reported as running elsewhere

    def _check_request(self, request: httpx.Request) -> None:
        """The name may resolve elsewhere by now (or only now): check it before each call."""
        try:
            check_host(request.url.host, self._resolve)
        except OSError as exc:
            raise httpx.ConnectError(f"cannot resolve {request.url.host}", request=request) from exc

    def close(self) -> None:
        self._client.close()

    # --- capabilities ----------------------------------------------------------------------

    def capabilities(self) -> frozenset[Capability]:
        if self._capabilities is None:
            if not (self._settings.caption_model or self._settings.plan_model):
                return frozenset()
            try:
                self._capabilities = self._detect()
            except NotLocalError as exc:
                log.warning("AI off: %s", exc)
                return frozenset()
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                return frozenset()  # server down or odd: ask again next time
        return self._capabilities

    def _detect(self) -> frozenset[Capability]:
        response = self._client.get("/api/tags")
        response.raise_for_status()
        names: list[str] = []
        for entry in response.json()["models"]:
            name = str(entry["name"])
            if is_cloud_model(name) or entry.get("remote_host"):
                self._refuse(name, entry.get("remote_host") or "ollama.com")
            else:
                names.append(name)
        found: set[Capability] = set()
        caption, plan = self._settings.caption_model, self._settings.plan_model
        if caption and any(_same_model(caption, n) for n in names) and self._has_vision(caption):
            found.add(Capability.CAPTION)
        if plan and any(_same_model(plan, n) for n in names):
            found.add(Capability.PLAN_ALBUM)
        return frozenset(found)

    def _has_vision(self, model: str) -> bool:
        response = self._client.post("/api/show", json={"model": model})
        response.raise_for_status()
        shown = response.json()
        if shown.get("remote_host"):
            self._refuse(model, shown["remote_host"])
            return False
        capabilities = shown.get("capabilities")
        # Older Ollama versions don't report capabilities: trust the configuration.
        return capabilities is None or "vision" in capabilities

    # --- caption ---------------------------------------------------------------------------

    def caption(self, image: bytes, lang: str) -> str:
        model = self._model(self._settings.caption_model, Capability.CAPTION)
        preview = self._downscale(image, self._settings.image_max_edge)
        message: dict[str, object] = {
            "role": "user",
            "content": f"Describe this photo in one short sentence, in the language '{lang}'.",
            "images": [base64.b64encode(preview).decode("ascii")],
        }
        messages: list[dict[str, object]] = [
            {"role": "system", "content": _CAPTION_SYSTEM},
            message,
        ]
        summary: dict[str, object] = {"lang": lang, "images": [{"bytes": len(preview)}]}
        return self._converse(
            Capability.CAPTION, model, messages, _CAPTION_SCHEMA, summary, self._parse_caption
        )

    def _parse_caption(self, content: str) -> str:
        data = _json(content)
        text = data.get("caption") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise _BadOutputError("the answer has no caption")
        if len(text.strip()) > self._settings.max_caption_chars:
            raise _BadOutputError(
                f"the caption is longer than {self._settings.max_caption_chars} characters"
            )
        return text.strip()

    # --- plan_album ------------------------------------------------------------------------

    def plan_album(self, prompt: str, context: LibrarySummary) -> AlbumPlan:
        model = self._model(self._settings.plan_model, Capability.PLAN_ALBUM)
        content = (
            f"{prompt}\n\nAllowed layout_hint values: {_layout_list(context.layouts)}\n"
            f"Photos (id|date|place|tags|description):\n{summary_lines(context)}"
        )
        messages: list[dict[str, object]] = [
            {"role": "system", "content": _PLAN_SYSTEM},
            {"role": "user", "content": content},
        ]
        schema = _plan_schema(context.layouts, self._settings.max_caption_chars)
        summary: dict[str, object] = {
            "prompt": prompt[:_LOGGED_TEXT],
            "photos": len(context.assets),
        }

        def parse(answer: str) -> AlbumPlan:
            try:
                plan = plan_from_json(_json(answer))
            except PlanFormatError as exc:
                raise _BadOutputError(str(exc)) from exc
            problems = validate(
                plan, context.asset_ids, context.layouts, self._settings.max_caption_chars
            )
            if problems:
                raise _BadOutputError("; ".join(problems))
            return plan

        return self._converse(Capability.PLAN_ALBUM, model, messages, schema, summary, parse)

    # --- the conversation with one retry ---------------------------------------------------

    def _refuse(self, model: str, host: object) -> None:
        log.warning("AI model %s refused: it runs on %s, not on this machine", model, host)
        self._remote.add(model)

    def _model(self, model: str | None, capability: Capability) -> str:
        if not model:
            raise AIUnavailableError(f"no model configured for {capability.value}")
        if model in self._remote:
            raise NotLocalError(f"the model {model} is a cloud model: only local ones run")
        return model

    def _converse(
        self,
        capability: Capability,
        model: str,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        summary: dict[str, object],
        parse: Callable[[str], T],
    ) -> T:
        problem = ""
        for attempt in (1, 2):
            call = _CallLog(capability, model, summary, attempt)
            content = self._chat(model, messages, schema, call)
            try:
                result = parse(content)
            except _BadOutputError as exc:
                problem = str(exc)
                self._log.record(call.done(content, ok=False, error=problem))
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"That answer is not usable: {problem}. Fix it."},
                ]
                continue
            self._log.record(call.done(content, ok=True))
            return result
        raise AIUnavailableError(f"the AI's answer was not usable twice: {problem}")

    def _chat(
        self,
        model: str,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        call: "_CallLog",
    ) -> str:
        body = {
            "model": model,
            "messages": messages,
            "format": schema,
            "stream": False,
            # Thinking models (qwen3, qwen3.5) otherwise reason at length first: minutes per album
            "think": False,
            "options": {"temperature": 0.2},
        }
        try:
            response = self._client.post("/api/chat", json=body)
        except NotLocalError as exc:
            self._log.record(call.done("", ok=False, error=str(exc)))
            raise
        except httpx.TimeoutException as exc:
            self._log.record(call.done("", ok=False, error="timeout"))
            raise AIUnreachableError("the AI server did not answer in time") from exc
        except httpx.HTTPError as exc:
            self._log.record(call.done("", ok=False, error=f"connection: {exc}"))
            raise AIUnreachableError(f"cannot reach the AI server: {exc}") from exc
        call.status = response.status_code
        if response.is_redirect:
            target = response.headers.get("location", "")
            self._log.record(call.done(target, ok=False, error="redirect not followed"))
            raise NotLocalError(f"the AI server redirected to {target}: not followed")
        if not response.is_success:
            detail = response.text[:500]
            self._log.record(call.done(detail, ok=False, error=f"HTTP {response.status_code}"))
            raise AIUnreachableError(f"the AI server refused the request: {detail}")
        remote = _remote_host(response)
        if remote:
            self._refuse(model, remote)
            self._log.record(call.done("", ok=False, error=f"answered by {remote}"))
            raise NotLocalError(f"the model {model} is a cloud model (answered by {remote})")
        return _message_content(response)


def _refuse_cloud_models(settings: OllamaSettings) -> None:
    for which, model in (("caption", settings.caption_model), ("plan", settings.plan_model)):
        if model and is_cloud_model(model):
            raise NotLocalError(
                f"the {which} model {model} is an Ollama cloud model (it runs on ollama.com): "
                "only local models are allowed"
            )


def _check_base_url(base_url: str, resolve: Resolve) -> None:
    """Stops the start when PA_OLLAMA_BASE_URL points off this machine and network. A name
    that does not resolve yet (the home server is off) is checked again on each request."""
    url = httpx.URL(base_url)
    if url.scheme not in ("http", "https") or not url.host:
        raise NotLocalError(f"PA_OLLAMA_BASE_URL={base_url} is not an http(s) address")
    try:
        check_host(url.host, resolve)
    except NotLocalError as exc:
        raise NotLocalError(f"PA_OLLAMA_BASE_URL={base_url}: {exc}") from exc
    except OSError:
        log.warning("AI server %s does not resolve yet: checked again on each request", url.host)


def _remote_host(response: httpx.Response) -> str | None:
    try:
        remote = response.json().get("remote_host")
    except (ValueError, AttributeError):
        return None
    return str(remote) if remote else None


def _message_content(response: httpx.Response) -> str:
    """The assistant's text; a malformed envelope becomes text the parser will reject."""
    try:
        content = response.json()["message"]["content"]
    except (ValueError, KeyError, TypeError):
        return response.text
    return content if isinstance(content, str) else json.dumps(content)


def _json(content: str) -> object:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise _BadOutputError(f"the answer is not valid JSON ({exc.msg})") from exc


class _CallLog:
    """Collects one attempt's summary and timing for the AI log."""

    def __init__(
        self, capability: Capability, model: str, summary: dict[str, object], attempt: int
    ) -> None:
        self.capability = capability
        self.model = model
        self.summary = summary
        self.attempt = attempt
        self.status: int | None = None
        self._started = time.monotonic()

    def done(self, content: str, *, ok: bool, error: str | None = None) -> AICall:
        return AICall(
            capability=self.capability.value,
            model=self.model,
            request=dict(self.summary),
            response={"status": self.status, "content": content[:_LOGGED_TEXT]},
            ok=ok,
            duration_ms=int((time.monotonic() - self._started) * 1000),
            error=error,
            attempt=self.attempt,
        )
