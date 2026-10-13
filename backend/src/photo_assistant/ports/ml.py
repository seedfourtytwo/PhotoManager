"""Ports for local ML (FEATURES 2.7 to 2.10, 3.5, 3.6, 4.6): encoders, face analysis, ML storage.

Models are optional at runtime: adapters load lazily and report ``status()``. When the model
files are missing, calls raise ``ModelUnavailableError`` and the job handlers record a
"model missing" status instead of failing forever.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.errors import UnavailableError
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from photo_assistant.domain.vectors import Vector

__all__ = [
    "BoundingBox",
    "Face",
    "FaceAnalyzer",
    "FaceChanges",
    "FaceMatches",
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
    "Visible",
]

# Which photos a read may show. A Viewer: the photos of that person's library, by the access
# rule, decided in SQL next to the query (people, similar photos). A collection of asset ids:
# exactly those (search hands over what is left after its filters).
Visible = Viewer | Collection[int]


class ModelUnavailableError(UnavailableError):
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
class FaceMatches:
    """What clustering asks about one face, within its reach."""

    count: int  # other faces within reach
    person_id: int | None  # the person of the nearest of them that has one


@dataclass(frozen=True, slots=True)
class FaceChanges:
    """The faces of a model against what the last finished global clustering pass kept
    (``keep_face_marks``), in the library: it outlives the process."""

    rule: str | None  # the settings that pass ran with; None: no pass has finished
    # Each face added, detected again, placed with a person or moved on in clustering since,
    # with its mark of now: a value that is different once any of that happens to the face.
    marks: Mapping[int, tuple[object, ...]]


@dataclass(frozen=True, slots=True)
class PersonSummary:
    id: int
    name: str | None
    cover_face: StoredFace | None  # a face the viewer may see
    face_count: int  # faces in assets the viewer may see
    asset_count: int
    hidden: bool  # left out of People: a stranger someone chose not to list


class MlStore(Protocol):
    """Embeddings, faces, people and tags. Every read that lists assets takes what the viewer
    may see (``Visible``) and never widens it."""

    def seen(self, asset_ids: Collection[int], visible: Visible) -> set[int]:
        """Those of ``asset_ids`` that ``visible`` covers."""
        ...

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
        self,
        query: Vector,
        model: str,
        candidates: Visible,
        limit: int,
        *,
        leave_out: int | None = None,
    ) -> list[ScoredAsset]:
        """Closest first; ``leave_out``: the photo the others are compared with."""
        ...

    # faces
    def replace_faces(self, asset_id: int, model: str, faces: Sequence[Face]) -> list[int]:
        """Drop this asset's model-assigned faces for the model and store new ones."""
        ...

    def faces_to_cluster(
        self, model: str, *, deferred: bool, asset_id: int | None = None
    ) -> list[int]: ...
    def face_matches(self, face_id: int, max_distance: float) -> FaceMatches: ...
    def face_changes(self, model: str) -> FaceChanges:
        """What is different from the marks kept, read in one go."""
        ...

    def keep_face_marks(
        self, model: str, rule: str, marks: Mapping[int, tuple[object, ...]]
    ) -> None:
        """All or nothing: these marks (those of faces that still exist) in place of the
        ones kept for the same faces, and ``rule`` as the settings of the last pass."""
        ...

    def deferred_faces_near(
        self, model: str, face_ids: Collection[int], max_distance: float
    ) -> list[int]:
        """The deferred faces with one of ``face_ids`` (other than itself) within reach."""
        ...

    def mark_deferred(self, face_id: int) -> None: ...
    def mark_clustered(self, face_id: int) -> None: ...
    def assign_face(self, face_id: int, person_id: int, *, by_user: bool = False) -> None: ...
    def create_person(self, cover_face_id: int) -> int: ...
    def faces_of_asset(self, asset_id: int) -> list[StoredFace]: ...
    def get_face(self, face_id: int) -> StoredFace | None: ...

    # people (visibility-scoped reads)
    def list_persons(self, visible: Visible, *, hidden: bool | None = False) -> list[PersonSummary]:
        """The listed people, the hidden ones (``True``) or both (``None``)."""
        ...

    def get_person(self, person_id: int, visible: Visible) -> PersonSummary | None: ...
    def rename_person(self, person_id: int, name: str | None) -> None: ...
    def set_person_hidden(self, person_id: int, hidden: bool) -> None: ...
    def merge_persons(self, target_id: int, source_ids: Sequence[int]) -> None: ...
    def move_faces(self, face_ids: Sequence[int], person_id: int) -> None: ...
    def create_empty_person(self, name: str | None) -> int: ...
    def person_asset_ids(self, person_id: int, visible: Visible) -> list[int]:
        """Newest first, like the timeline."""
        ...

    def delete_empty_persons(self) -> int: ...

    # tags
    def replace_model_tags(
        self, asset_id: int, model: str, tags: Sequence[TagScore], screen_or_document: bool
    ) -> None: ...
    def tags_of(self, asset_id: int) -> list[TagScore]: ...
    def is_screen_or_document(self, asset_id: int) -> bool | None: ...
    def asset_ids_with_tag(self, name: str, visible: Visible) -> list[int]: ...
    def screen_or_document_ids(self, visible: Visible) -> list[int]: ...
