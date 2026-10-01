"""Ports for local ML (FEATURES 2.7 to 2.10, 3.5, 3.6, 4.6): encoders, face analysis, ML storage.

Models are optional at runtime: adapters load lazily and report ``status()``. When the model
files are missing, calls raise ``ModelUnavailableError`` and the job handlers record a
"model missing" status instead of failing forever.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from photo_assistant.domain.vectors import Vector

__all__ = [
    "BoundingBox",
    "Face",
    "FaceAnalyzer",
    "ImageEmbedder",
    "MlStore",
    "ModelFormatError",
    "ModelInfo",
    "ModelStatus",
    "ModelUnavailableError",
    "PersonSummary",
    "ScoredAsset",
    "StoredFace",
    "TextEmbedder",
]


class ModelUnavailableError(RuntimeError):
    """The model files are not on this machine (run `just models`), or can't be loaded."""


class ModelFormatError(ModelUnavailableError):
    """The files exist but don't look like the model we expect (names, shapes, dimensions)."""


@dataclass(frozen=True, slots=True)
class ModelInfo:
    name: str  # storage key, e.g. "ViT-B-32__openai" or "buffalo_l"
    dim: int  # embedding length


@dataclass(frozen=True, slots=True)
class ModelStatus:
    ready: bool
    detail: str  # what is missing and what to do, or which provider is in use


class _Model(Protocol):
    @property
    def name(self) -> str:
        """Known without touching the files (used as the storage key)."""
        ...

    def info(self) -> ModelInfo:
        """Loads the model if needed; raises ModelUnavailableError."""
        ...

    def status(self) -> ModelStatus: ...


class ImageEmbedder(_Model, Protocol):
    def embed_images(self, paths: Sequence[Path]) -> list[Vector]:
        """One L2-normalised vector per image, same order."""
        ...


class TextEmbedder(_Model, Protocol):
    def embed_text(self, text: str) -> Vector:
        """L2-normalised, in the same space as the paired ImageEmbedder."""
        ...


class FaceAnalyzer(_Model, Protocol):
    def detect(self, path: Path) -> list[Face]:
        """Faces in the image as displayed (orientation applied), best score first."""
        ...


@dataclass(frozen=True, slots=True)
class ScoredAsset:
    asset_id: int
    score: float  # cosine similarity, higher is closer


@dataclass(frozen=True, slots=True)
class StoredFace:
    id: int
    asset_id: int
    box: BoundingBox
    score: float
    person_id: int | None


@dataclass(frozen=True, slots=True)
class PersonSummary:
    id: int
    name: str | None
    cover_face: StoredFace | None  # a face the viewer may see
    face_count: int  # faces in assets the viewer may see
    asset_count: int


class MlStore(Protocol):
    """Embeddings, faces, people and tags. Every read that lists assets takes the ids the
    viewer may see (computed by the visibility function elsewhere) and never widens them."""

    # task bookkeeping: status per (asset, task, model), e.g. "done", "model_missing"
    def task_status(self, asset_id: int, task: str, model: str) -> str | None: ...
    def set_task_status(
        self, asset_id: int, task: str, model: str, status: str, detail: str | None = None
    ) -> None: ...
    def assets_with_status(self, task: str, model: str, status: str) -> list[int]: ...

    # CLIP
    def save_clip(self, asset_id: int, model: str, vector: Vector) -> None: ...
    def clip_vector(self, asset_id: int, model: str) -> Vector | None: ...
    def nearest_assets(
        self, query: Vector, model: str, candidates: Collection[int], limit: int
    ) -> list[ScoredAsset]: ...

    # faces
    def replace_faces(self, asset_id: int, model: str, faces: Sequence[Face]) -> list[int]:
        """Drop this asset's model-assigned faces for the model and store new ones."""
        ...

    def faces_to_cluster(
        self, model: str, *, deferred: bool, asset_id: int | None = None
    ) -> list[int]: ...
    def count_face_matches(self, face_id: int, max_distance: float, limit: int) -> int: ...
    def nearest_person(self, face_id: int, max_distance: float) -> int | None: ...
    def mark_deferred(self, face_id: int) -> None: ...
    def mark_clustered(self, face_id: int) -> None: ...
    def assign_face(self, face_id: int, person_id: int, *, by_user: bool = False) -> None: ...
    def create_person(self, cover_face_id: int) -> int: ...
    def faces_of_asset(self, asset_id: int) -> list[StoredFace]: ...
    def get_face(self, face_id: int) -> StoredFace | None: ...

    # people (visibility-scoped reads)
    def list_persons(self, visible: Collection[int]) -> list[PersonSummary]: ...
    def get_person(self, person_id: int, visible: Collection[int]) -> PersonSummary | None: ...
    def rename_person(self, person_id: int, name: str | None) -> None: ...
    def merge_persons(self, target_id: int, source_ids: Sequence[int]) -> None: ...
    def move_faces(self, face_ids: Sequence[int], person_id: int) -> None: ...
    def create_empty_person(self, name: str | None) -> int: ...
    def person_asset_ids(self, person_id: int, visible: Collection[int]) -> list[int]: ...
    def delete_empty_persons(self) -> int: ...

    # tags
    def replace_model_tags(
        self, asset_id: int, model: str, tags: Sequence[TagScore], screen_or_document: bool
    ) -> None: ...
    def tags_of(self, asset_id: int) -> list[TagScore]: ...
    def is_screen_or_document(self, asset_id: int) -> bool | None: ...
    def asset_ids_with_tag(self, name: str, visible: Collection[int]) -> list[int]: ...
    def screen_or_document_ids(self, visible: Collection[int]) -> list[int]: ...
