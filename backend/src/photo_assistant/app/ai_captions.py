"""Background captions (FEATURES 7.3): the local vision model describes the photos that have no
description yet. The text is a derived field, like the auto tags: it feeds the album-naming
prompt so titles describe what is in the photos, and changes nothing about a photo.

One job is one batch of the photos still without a caption, oldest first; a full batch queues
the next. A photo the model cannot describe is remembered and not asked again. An AI server
that does not answer fails the job, so the worker tries it again later; what was done is kept.
On the home server (no GPU) one caption takes about half a minute, so this runs on its own
worker thread, never in a request.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from photo_assistant.ports.ai import AIProvider, AIUnavailableError, AIUnreachableError, Capability

CAPTION_JOB = "ai_captions"
BATCH = 20  # about ten minutes on the home server's CPU, a minute on the laptop's GPU
CAPTION_LANG = "en"  # the app's language


class CaptionStore(Protocol):
    def photos_to_caption(self, model: str, limit: int) -> list[tuple[int, str]]: ...
    def save_caption(self, asset_id: int, text: str, model: str, lang: str) -> None: ...
    def caption_failed(self, asset_id: int, model: str, detail: str) -> None: ...
    def enqueue_once(self, kind: str, payload: dict[str, object] | None = None) -> int | None: ...


class CaptionPhotos:
    """Job handler; the payload is empty."""

    def __init__(
        self,
        store: CaptionStore,
        ai: AIProvider,
        model: str,
        absolute: Callable[[str], Path],
        batch: int = BATCH,
    ) -> None:
        self._store, self._ai, self._model = store, ai, model
        self._absolute, self._batch = absolute, batch

    def __call__(self, payload: dict[str, object]) -> int:
        """How many photos got a caption."""
        if Capability.CAPTION not in self._ai.capabilities():
            return 0  # off or down: the periodic check queues this again
        todo = self._store.photos_to_caption(self._model, self._batch)
        done = sum(self._describe(asset_id, path) for asset_id, path in todo)
        if len(todo) == self._batch:
            self._store.enqueue_once(CAPTION_JOB)
        return done

    def _describe(self, asset_id: int, path: str) -> bool:
        try:
            image = self._absolute(path).read_bytes()
        except OSError as exc:
            self._store.caption_failed(asset_id, self._model, f"cannot read the photo: {exc}")
            return False
        try:
            text = self._ai.caption(image, CAPTION_LANG)
        except AIUnreachableError:
            raise
        except AIUnavailableError as exc:
            self._store.caption_failed(asset_id, self._model, str(exc))
            return False
        self._store.save_caption(asset_id, text, self._model, CAPTION_LANG)
        return True

