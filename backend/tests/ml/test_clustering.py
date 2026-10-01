"""Incremental face clustering (Immich-style): decisions + the reference batch algorithm."""

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from photo_assistant.domain.clustering import (
    Action,
    ClusterParams,
    Decision,
    cluster,
    decide,
)
from photo_assistant.domain.vectors import Vector, cosine_distance

P = ClusterParams(max_distance=0.5, min_faces=3)


# --- decide ---------------------------------------------------------------------------------


def test_face_without_any_match_is_skipped() -> None:
    assert decide(0, None, P, deferred=False) == Decision(Action.SKIP)


def test_non_core_face_is_deferred_first_time_even_near_a_person() -> None:
    assert decide(1, 7, P, deferred=False) == Decision(Action.DEFER)


def test_deferred_non_core_face_joins_nearest_person() -> None:
    assert decide(1, 7, P, deferred=True) == Decision(Action.ASSIGN, 7)


def test_deferred_non_core_face_without_person_stays_unassigned() -> None:
    assert decide(1, None, P, deferred=True) == Decision(Action.SKIP)


def test_core_face_joins_nearest_person() -> None:
    assert decide(2, 4, P, deferred=False) == Decision(Action.ASSIGN, 4)


def test_core_face_without_person_starts_a_new_person() -> None:
    assert decide(2, None, P, deferred=False) == Decision(Action.NEW_PERSON)


def test_min_faces_one_makes_every_face_core() -> None:
    assert decide(0, None, ClusterParams(0.5, 1), deferred=False) == Decision(Action.NEW_PERSON)


@pytest.mark.parametrize(("distance", "faces"), [(0.0, 3), (2.5, 3), (0.5, 0)])
def test_params_are_validated(distance: float, faces: int) -> None:
    with pytest.raises(ValueError):
        ClusterParams(distance, faces)


# --- reference batch algorithm ---------------------------------------------------------------


def blob(centre: int, n: int, dim: int, rng: random.Random, first_id: int) -> dict[int, Vector]:
    out = {}
    for i in range(n):
        v = [rng.uniform(-0.05, 0.05) for _ in range(dim)]
        v[centre] += 1.0
        out[first_id + i] = tuple(v)
    return out


def test_two_well_separated_groups_become_two_people() -> None:
    rng = random.Random(1)
    faces = blob(0, 4, 6, rng, 1) | blob(1, 5, 6, rng, 10)
    result = cluster(faces, P)
    assert len({result[i] for i in range(1, 5)}) == 1
    assert len({result[i] for i in range(10, 15)}) == 1
    assert result[1] != result[10]
    assert None not in result.values()


def test_group_smaller_than_min_faces_stays_unassigned() -> None:
    rng = random.Random(2)
    faces = blob(0, 2, 6, rng, 1) | blob(1, 3, 6, rng, 10)
    result = cluster(faces, P)
    assert result[1] is None and result[2] is None
    assert result[10] is not None


def test_small_group_near_an_existing_person_joins_it_on_the_deferred_pass() -> None:
    # unit vectors at 0°, 10°, 20°, 75°: cosine distance ≤ 0.5 means ≤ 60° apart, so face 4
    # has one neighbour (face 3) → not core → deferred → joins face 3's person.
    faces = {
        i: (math.cos(math.radians(a)), math.sin(math.radians(a)))
        for i, a in [(1, 0), (2, 10), (3, 20), (4, 75)]
    }
    result = cluster(faces, P)
    assert result[4] == result[1] is not None


def test_existing_assignments_are_kept_and_reused() -> None:
    rng = random.Random(3)
    faces = blob(0, 4, 6, rng, 1)
    result = cluster(faces, P, existing={1: 42})
    assert result == {1: 42, 2: 42, 3: 42, 4: 42}


def test_new_person_ids_follow_the_given_start() -> None:
    faces = blob(0, 3, 4, random.Random(4), 1)
    assert set(cluster(faces, P, first_person_id=100).values()) == {100}


# --- properties --------------------------------------------------------------------------------

face_sets = st.dictionaries(
    st.integers(min_value=1, max_value=60),
    st.lists(st.floats(-1, 1, allow_nan=False), min_size=3, max_size=3).filter(
        lambda v: sum(x * x for x in v) > 0.01
    ),
    min_size=1,
    max_size=25,
)
params = st.builds(ClusterParams, st.floats(0.05, 1.0), st.integers(min_value=1, max_value=4))


def as_vectors(raw: dict[int, list[float]]) -> dict[int, Vector]:
    return {k: tuple(v) for k, v in raw.items()}


@settings(max_examples=60, deadline=None)
@given(face_sets, params)
def test_clustering_is_deterministic_and_order_independent(
    raw: dict[int, list[float]], p: ClusterParams
) -> None:
    faces = as_vectors(raw)
    shuffled = dict(sorted(faces.items(), reverse=True))
    assert cluster(faces, p) == cluster(shuffled, p) == cluster(faces, p)


@settings(max_examples=60, deadline=None)
@given(face_sets, params)
def test_every_assigned_face_has_a_close_face_unless_min_faces_is_one(
    raw: dict[int, list[float]], p: ClusterParams
) -> None:
    faces = as_vectors(raw)
    result = cluster(faces, p)
    for fid, person in result.items():
        if person is None or p.min_faces == 1:
            continue
        others = [cosine_distance(faces[fid], faces[o]) for o in faces if o != fid]
        assert any(d <= p.max_distance for d in others)


@settings(max_examples=60, deadline=None)
@given(face_sets, st.floats(0.05, 1.0))
def test_min_faces_one_assigns_everyone(raw: dict[int, list[float]], distance: float) -> None:
    result = cluster(as_vectors(raw), ClusterParams(distance, 1))
    assert None not in result.values()


@settings(max_examples=60, deadline=None)
@given(face_sets, params)
def test_rerunning_on_the_result_changes_nothing(
    raw: dict[int, list[float]], p: ClusterParams
) -> None:
    faces = as_vectors(raw)
    first = cluster(faces, p)
    kept = {k: v for k, v in first.items() if v is not None}
    again = cluster(faces, p, existing=kept, first_person_id=1000)
    assert {k: v for k, v in again.items() if k in kept} == kept
