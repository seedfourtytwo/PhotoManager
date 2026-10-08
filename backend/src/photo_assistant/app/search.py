"""Natural-language search and "more like this" (FEATURES 3.5, 3.6).

Search takes ``candidates``: the asset ids the viewer may see *after* the facet filters
(computed by the visibility function and SQL filters elsewhere). "More like this" takes the
viewer, or such a set. Both only rank within that.
"""

from collections.abc import Collection

from photo_assistant.domain.errors import ConflictError, UnavailableError
from photo_assistant.domain.search_query import ParsedQuery, parse_query
from photo_assistant.ports.ml import (
    MlStore,
    ModelUnavailableError,
    ScoredAsset,
    TextEmbedder,
    Visible,
)

__all__ = [
    "NotIndexedError",
    "ParsedQuery",
    "SearchUnavailableError",
    "SemanticSearch",
    "SimilarPhotos",
    "parse_query",
]


class SearchUnavailableError(UnavailableError):
    """No CLIP model on this machine; the API answers 503 and the UI falls back to keywords."""


class NotIndexedError(ConflictError):
    """The photo has no embedding yet (still queued, or the model is missing)."""


class SemanticSearch:
    def __init__(self, text: TextEmbedder, store: MlStore, *, min_score: float | None = None):
        self._text, self._store, self._min_score = text, store, min_score

    def __call__(self, text: str, candidates: Collection[int], limit: int) -> list[ScoredAsset]:
        if not text.strip():
            return []
        try:
            query = self._text.embed_text(text)
        except ModelUnavailableError as exc:
            raise SearchUnavailableError(str(exc)) from exc
        hits = self._store.nearest_assets(query, self._text.name, candidates, limit)
        if self._min_score is None:
            return hits
        return [hit for hit in hits if hit.score >= self._min_score]


class SimilarPhotos:
    def __init__(self, store: MlStore, model: str) -> None:
        self._store, self._model = store, model

    def __call__(self, asset_id: int, candidates: Visible, limit: int) -> list[ScoredAsset]:
        if not self._store.seen([asset_id], candidates):
            raise LookupError(f"no asset {asset_id}")  # hidden from this viewer → 404
        vector = self._store.clip_vector(asset_id, self._model)
        if vector is None:
            raise NotIndexedError(f"asset {asset_id} has not been analysed yet")
        return self._store.nearest_assets(
            vector, self._model, candidates, limit, leave_out=asset_id
        )
