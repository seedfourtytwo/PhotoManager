"""AI plans for suggested albums (FEATURES 5.6, 7.3): the local model names an event, splits it
into sections and writes short captions, in the background.

The app chooses the photos (``domain.events``); the model only gets one event's photos, must use
each once (``domain.album_plan.validate``) and never adds one. On the home server (no GPU) a
plan takes one to two minutes, so it is a job: a suggestion shows the plain title until its
plan is stored, and keeps it when the AI is off, fails, or the plan was made for other photos
(the event grew, or this viewer sees a different part of it). A plan the model failed is not
asked again until the server restarts; a server that does not answer fails the job, which the
worker tries again later.
"""

from collections.abc import Sequence
from typing import Protocol

from photo_assistant.app import album_suggestions
from photo_assistant.app.ai_captions import CaptionPhotos
from photo_assistant.app.album_suggestions import Suggestion, SuggestionStore
from photo_assistant.domain.access import User, Viewer
from photo_assistant.domain.album_plan import AlbumPlan, AssetSummary, LibrarySummary
from photo_assistant.domain.events import Event, album_events, event_title
from photo_assistant.domain.print_layout import LAYOUTS
from photo_assistant.ports.ai import AIProvider, AIUnavailableError, AIUnreachableError, Capability

PLAN_JOB = "ai_album_plan"
# One line per photo in the prompt: more than this does not fit a small model's context
MAX_PLAN_PHOTOS = 60
PHOTO_LAYOUTS = {lay.id: lay.capacity for lay in LAYOUTS.values() if lay.capacity > 0}
_PROMPT = (
    "Name and arrange the photos of one event as an album, in English. Its plain title, from "
    "its dates and places, is '{plain}': keep what is true in it and say what the photos show."
)


class PlanStore(SuggestionStore, Protocol):
    def get_user(self, user_id: int) -> User | None: ...
    def album_plan(self, key: str, photos: str) -> AlbumPlan | None: ...
    def save_album_plan(self, key: str, photos: str, model: str, plan: AlbumPlan) -> None: ...
    def captions_of(self, asset_ids: Sequence[int]) -> dict[int, str]: ...
    def tags_of_assets(self, asset_ids: Sequence[int]) -> dict[int, tuple[str, ...]]: ...
    def enqueue_once(self, kind: str, payload: dict[str, object] | None = None) -> int | None: ...


def photos_key(asset_ids: Sequence[int]) -> str:
    """Which photos a plan was made for: their ids, sorted."""
    return ",".join(str(i) for i in sorted(asset_ids))


class AlbumPlanner:
    """The suggestions with their AI titles, and the job handler that makes the plans.
    ``model``: the configured plan model; None = the AI is off."""

    def __init__(
        self,
        store: PlanStore,
        ai: AIProvider,
        model: str | None,
        captions: CaptionPhotos | None = None,
    ) -> None:
        self._store, self._ai, self._model, self._captions = store, ai, model, captions
        self._failed: set[tuple[str, str]] = set()

    def namer(self, event: Event) -> str:
        plan = self._plan_for(event.key, [p.asset_id for p in event.photos])
        return plan.title if plan else event_title(event)

    def suggestions(self, viewer: Viewer) -> list[Suggestion]:
        """What Home shows; the ones without a plan get one queued."""
        found = album_suggestions.suggestions(self._store, viewer, self.namer)
        for s in found:
            if self._wanted(s.key, s.asset_ids):
                self._store.enqueue_once(PLAN_JOB, {"user_id": viewer.user_id, "key": s.key})
        return found

    def __call__(self, payload: dict[str, object]) -> bool:
        """Job handler, ``{"user_id": n, "key": event key}``. True when a plan was stored."""
        user = self._store.get_user(int(str(payload["user_id"])))
        event = self._event(Viewer.of(user), str(payload["key"])) if user else None
        if event is None:
            return False  # the account or the event is gone
        ids = [p.asset_id for p in event.photos]
        if not self._wanted(event.key, ids) or Capability.PLAN_ALBUM not in self._ai.capabilities():
            return False
        if self._captions is not None:
            self._captions.describe(ids)
        try:
            plan = self._ai.plan_album(
                _PROMPT.format(plain=event_title(event)), self._summary(event)
            )
        except AIUnreachableError:
            raise
        except AIUnavailableError:
            self._failed.add((event.key, photos_key(ids)))
            return False
        assert self._model is not None  # _wanted
        self._store.save_album_plan(event.key, photos_key(ids), self._model, plan)
        return True

    def _plan_for(self, key: str, asset_ids: Sequence[int]) -> AlbumPlan | None:
        return self._store.album_plan(key, photos_key(asset_ids)) if self._model else None

    def _wanted(self, key: str, asset_ids: Sequence[int]) -> bool:
        return (
            self._model is not None
            and len(asset_ids) <= MAX_PLAN_PHOTOS
            and (key, photos_key(asset_ids)) not in self._failed
            and self._plan_for(key, asset_ids) is None
        )

    def _event(self, viewer: Viewer, key: str) -> Event | None:
        events = album_events(self._store.event_photos(viewer))
        return next((e for e in events if e.key == key), None)

    def _summary(self, event: Event) -> LibrarySummary:
        ids = [p.asset_id for p in event.photos]
        captions, tags = self._store.captions_of(ids), self._store.tags_of_assets(ids)
        assets = tuple(
            AssetSummary(
                p.asset_id,
                p.taken_at.date().isoformat() if p.taken_at else "",
                p.place.label if p.place else None,
                tags.get(p.asset_id, ()),
                captions.get(p.asset_id),
            )
            for p in event.photos
        )
        return LibrarySummary(assets, PHOTO_LAYOUTS)
