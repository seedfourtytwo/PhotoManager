"""Incremental face clustering, the way Immich does it (DBSCAN-like, one face at a time).

A face is *core* when at least ``min_faces`` faces (itself included) lie within
``max_distance`` (cosine distance) of it. Core faces join the nearest person within reach or
start a new one. Non-core faces are deferred once; on the deferred pass they join the nearest
person within reach, or stay unassigned. Faces a user placed are never moved.

``decide`` is what the job pipeline uses (neighbours come from sqlite-vec); ``cluster`` is the
same algorithm over an in-memory set — the reference the property tests and the app's
equivalence test check against.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from photo_assistant.domain.vectors import Vector, cosine_distance


@dataclass(frozen=True, slots=True)
class ClusterParams:
    max_distance: float = 0.5  # Immich's default for ArcFace embeddings
    min_faces: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.max_distance <= 2.0:
            raise ValueError(f"max_distance must be in (0, 2], got {self.max_distance}")
        if self.min_faces < 1:
            raise ValueError(f"min_faces must be ≥ 1, got {self.min_faces}")


class Action(StrEnum):
    ASSIGN = "assign"
    NEW_PERSON = "new_person"
    DEFER = "defer"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    person_id: int | None = None


def decide(
    other_matches: int, nearest_person: int | None, params: ClusterParams, *, deferred: bool
) -> Decision:
    """``other_matches``: faces other than this one within ``max_distance``.

    ``nearest_person``: person of the closest assigned face within ``max_distance``."""
    count = other_matches + 1
    if params.min_faces > 1 and count <= 1:
        return Decision(Action.SKIP)
    is_core = count >= params.min_faces
    if not is_core and not deferred:
        return Decision(Action.DEFER)
    if nearest_person is not None:
        return Decision(Action.ASSIGN, nearest_person)
    if is_core:
        return Decision(Action.NEW_PERSON)
    return Decision(Action.SKIP)


def _neighbours(face_id: int, faces: Mapping[int, Vector], max_distance: float) -> list[int]:
    """Other faces within reach, nearest first (ties by id, so results are deterministic)."""
    scored = [
        (cosine_distance(faces[face_id], vector), other)
        for other, vector in faces.items()
        if other != face_id
    ]
    return [other for d, other in sorted(scored) if d <= max_distance]


class _Run:
    def __init__(
        self, faces: Mapping[int, Vector], params: ClusterParams, persons: dict[int, int | None]
    ) -> None:
        self.faces, self.params, self.persons = faces, params, persons

    def step(self, face_id: int, next_person: int, *, deferred: bool) -> tuple[Decision, int]:
        near = _neighbours(face_id, self.faces, self.params.max_distance)
        person = next((self.persons[n] for n in near if self.persons[n] is not None), None)
        decision = decide(len(near), person, self.params, deferred=deferred)
        if decision.action is Action.ASSIGN:
            self.persons[face_id] = decision.person_id
        elif decision.action is Action.NEW_PERSON:
            self.persons[face_id] = next_person
            next_person += 1
        return decision, next_person


def cluster(
    faces: Mapping[int, Vector],
    params: ClusterParams,
    *,
    existing: Mapping[int, int] | None = None,
    first_person_id: int = 1,
) -> dict[int, int | None]:
    """Face id → person id (None = unassigned). Processes new faces in id order."""
    persons: dict[int, int | None] = {face_id: None for face_id in faces}
    persons.update(existing or {})
    run = _Run(faces, params, persons)
    next_person = first_person_id
    deferred: list[int] = []
    for face_id in sorted(f for f in faces if persons[f] is None):
        decision, next_person = run.step(face_id, next_person, deferred=False)
        if decision.action is Action.DEFER:
            deferred.append(face_id)
    for face_id in deferred:
        _, next_person = run.step(face_id, next_person, deferred=True)
    return persons
