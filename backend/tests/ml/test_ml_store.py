"""SqliteMlStore against real SQLite + sqlite-vec (in memory)."""

import math
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore, from_blob, to_blob
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from photo_assistant.domain.vectors import Vector, cosine_distance
from photo_assistant.ports.ml import FaceChanges, FaceMatches
from tests.adapters.test_visibility_rule import ROLES, _random_library
from tests.factories import NOW, new_asset

M = "test-model"


def assets(repo: SqliteRepository, n: int) -> list[int]:
    return [repo.add_asset(new_asset(i), NOW) for i in range(1, n + 1)]


def angle(deg: float) -> Vector:
    return (math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0)


def face(vector: Vector, score: float = 0.9) -> Face:
    return Face(BoundingBox(0.1, 0.2, 0.3, 0.4), score, ((0.2, 0.3),) * 5, vector)


def test_blob_round_trip_is_float32_little_endian() -> None:
    blob = to_blob((1.0, -2.5))
    assert blob == b"\x00\x00\x80?\x00\x00 \xc0"
    assert from_blob(blob) == (1.0, -2.5)


def test_migration_creates_the_ml_tables(conn: sqlite3.Connection) -> None:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"clip_embedding", "face", "person", "tag", "asset_tag", "ml_task"} <= names


def test_the_ml_store_on_a_database_file_migrates_and_loads_sqlite_vec(tmp_path: Path) -> None:
    store = SqliteMlStore(Database.open(tmp_path / "library.db"))
    assert store.vec_version().startswith("v")
    store.close()


# --- task status ------------------------------------------------------------------------------


def test_task_status_round_trip(repo: SqliteRepository, store: SqliteMlStore) -> None:
    (a, b) = assets(repo, 2)
    assert store.task_status(a, "embed_clip", M) is None
    store.set_task_status(a, "embed_clip", M, "model_missing", "run just models")
    store.set_task_status(b, "embed_clip", M, "model_missing")
    store.set_task_status(b, "embed_clip", M, "done")
    assert store.task_status(a, "embed_clip", M) == "model_missing"
    assert store.assets_with_status("embed_clip", M, "model_missing") == [a]


# --- CLIP -------------------------------------------------------------------------------------


def test_clip_vectors_are_keyed_by_asset_and_model(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a,) = assets(repo, 1)
    store.save_clip(a, M, (1.0, 0.0, 0.0))
    store.save_clip(a, M, (0.0, 1.0, 0.0))  # replace
    store.save_clip(a, "other", (0.0, 0.0, 1.0))
    assert store.clip_vector(a, M) == (0.0, 1.0, 0.0)
    assert store.clip_vector(a, "missing") is None


def test_nearest_assets_ranks_within_candidates_only(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    ids = assets(repo, 4)
    for asset_id, deg in zip(ids, [0, 30, 60, 90], strict=True):
        store.save_clip(asset_id, M, angle(deg))
    hits = store.nearest_assets(angle(10), M, candidates={ids[1], ids[2], ids[3]}, limit=2)
    assert [h.asset_id for h in hits] == [ids[1], ids[2]]
    assert hits[0].score == pytest.approx(math.cos(math.radians(20)), abs=1e-6)
    assert store.nearest_assets(angle(0), M, candidates=set(), limit=5) == []
    assert store.nearest_assets(angle(0), "other", candidates=set(ids), limit=5) == []


def test_a_stored_embedding_without_a_direction_does_not_break_search(
    conn: sqlite3.Connection, repo: SqliteRepository, store: SqliteMlStore
) -> None:
    """A zero vector has no angle to anything (the distance is NULL): it is left out."""
    (good, zero) = assets(repo, 2)
    store.save_clip(good, M, angle(0))
    conn.execute(  # as an older version may have stored it
        "INSERT INTO clip_embedding (model, asset_id, dim, embedding) VALUES (?, ?, 3, ?)",
        (M, zero, to_blob((0.0, 0.0, 0.0))),
    )
    hits = store.nearest_assets(angle(10), M, candidates=[good, zero], limit=5)
    assert [h.asset_id for h in hits] == [good]
    assert store.nearest_assets((0.0, 0.0, 0.0), M, candidates=[good, zero], limit=5) == []


@pytest.mark.parametrize(
    "vector", [(0.0, 0.0, 0.0), (1.0, math.nan, 0.0), (math.inf, 0.0, 0.0), ()]
)
def test_an_embedding_without_a_direction_is_not_stored(
    repo: SqliteRepository, store: SqliteMlStore, vector: Vector
) -> None:
    (a,) = assets(repo, 1)
    with pytest.raises(ValueError, match="embedding"):
        store.save_clip(a, M, vector)
    assert store.clip_vector(a, M) is None


def test_a_face_without_a_direction_matches_nobody_and_breaks_nothing(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a,) = assets(repo, 1)
    good, zero = store.replace_faces(a, M, [face(angle(0)), face((0.0, 0.0, 0.0))])
    assert store.face_matches(good, 2.0) == FaceMatches(0, None)
    assert store.face_matches(zero, 2.0) == FaceMatches(0, None)


@pytest.mark.parametrize("broken", [(0.0, 0.0, 0.0), (math.nan, 1.0, 0.0), (math.inf, 0.0, 0.0)])
def test_a_named_face_without_a_direction_is_nobodys_nearest_person(
    repo: SqliteRepository, store: SqliteMlStore, broken: Vector
) -> None:
    """Its distance is NULL also where the nearest person is picked by ORDER BY distance."""
    (a,) = assets(repo, 1)
    good, bad, near = store.replace_faces(a, M, [face(angle(0)), face(broken), face(angle(5))])
    nobody = store.create_person(bad)
    assert store.face_matches(good, 2.0) == FaceMatches(1, None)
    assert store.face_matches(bad, 2.0) == FaceMatches(0, None)
    somebody = store.create_person(near)
    assert store.face_matches(good, 2.0) == FaceMatches(1, somebody)
    assert somebody != nobody


def test_the_candidate_set_is_filled_in_one_transaction(
    conn: sqlite3.Connection, repo: SqliteRepository, store: SqliteMlStore
) -> None:
    """In autocommit every candidate row is its own transaction (slow for a whole library)."""
    ids = assets(repo, 3)
    autocommit: list[str] = []

    def note(statement: str) -> None:
        if statement.startswith("INSERT OR IGNORE INTO temp.ml_candidates"):
            autocommit.append("in a transaction" if conn.in_transaction else "on its own")

    conn.set_trace_callback(note)
    try:
        assert store.nearest_assets(angle(0), M, candidates=ids, limit=5) == []
    finally:
        conn.set_trace_callback(None)
    assert autocommit == ["in a transaction"] * 3
    assert not conn.in_transaction, "the fill is committed before the query runs"


def test_the_candidate_set_can_be_filled_inside_a_transaction(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a,) = assets(repo, 1)
    store.replace_model_tags(a, M, [TagScore("beach", 0.9)], screen_or_document=False)
    with repo._transaction():
        assert store.asset_ids_with_tag("beach", visible=[a]) == [a]
        assert repo._conn.in_transaction, "the caller's transaction stays open"


# --- faces and clustering primitives ----------------------------------------------------------


def test_replace_faces_stores_geometry_and_replaces_on_rerun(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a,) = assets(repo, 1)
    first = store.replace_faces(a, M, [face(angle(0)), face(angle(5))])
    assert len(first) == 2
    (only,) = store.replace_faces(a, M, [face(angle(10), score=0.8)])
    (stored,) = store.faces_of_asset(a)
    assert stored.id == only and stored.score == pytest.approx(0.8)
    assert stored.box == BoundingBox(
        pytest.approx(0.1),  # type: ignore[arg-type]
        pytest.approx(0.2),  # type: ignore[arg-type]
        pytest.approx(0.3),  # type: ignore[arg-type]
        pytest.approx(0.4),  # type: ignore[arg-type]
    )
    assert store.get_face(only) == stored
    assert store.get_face(9999) is None


def test_ml_writes_join_a_transaction_that_is_already_open(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    """They go through the Database's one transaction(), like every other store."""
    (a,) = assets(repo, 1)
    with pytest.raises(RuntimeError, match="undo"), repo._transaction():
        store.replace_faces(a, M, [face(angle(0))])
        raise RuntimeError("undo")
    assert store.faces_of_asset(a) == []


def test_face_matches_and_nearest_person(repo: SqliteRepository, store: SqliteMlStore) -> None:
    (a, b) = assets(repo, 2)
    f1, f2 = store.replace_faces(a, M, [face(angle(0)), face(angle(20))])
    (f3,) = store.replace_faces(b, M, [face(angle(80))])
    reach = 1 - math.cos(math.radians(30))
    assert store.face_matches(f1, reach) == FaceMatches(1, None)
    assert store.face_matches(f3, reach) == FaceMatches(0, None)
    person = store.create_person(f2)
    assert store.face_matches(f1, reach) == FaceMatches(1, person)
    assert store.get_face(f2).person_id == person  # type: ignore[union-attr]


# The two statements face_matches replaced: the oracle for the one that does both.
_OLD_NEIGHBOURS = (
    "FROM face f JOIN face me ON me.id = ? "
    "WHERE f.model = me.model AND f.dim = me.dim AND f.id != me.id "
    "AND vec_distance_cosine(f.embedding, me.embedding) <= ?"
)
_OLD_COUNT = f"SELECT count(*) FROM (SELECT 1 {_OLD_NEIGHBOURS})"
_OLD_NEAREST = (
    f"SELECT f.person_id {_OLD_NEIGHBOURS} AND f.person_id IS NOT NULL "
    "ORDER BY vec_distance_cosine(f.embedding, me.embedding), f.id LIMIT 1"
)


def random_faces(rng: random.Random, n: int) -> list[Face]:
    """Half of them in three tight bunches, the rest anywhere; a few without a direction."""
    centres = [tuple(rng.gauss(0, 1) for _ in range(5)) for _ in range(3)]
    vectors: list[Vector] = []
    for _ in range(n):
        centre = rng.choice(centres) if rng.random() < 0.5 else (0.0,) * 5
        vectors.append(tuple(c + rng.gauss(0, 0.3 if any(centre) else 1) for c in centre))
    vectors[rng.randrange(n)] = (0.0,) * 5
    return [face(v) for v in vectors]


@pytest.mark.parametrize("seed", range(5))
def test_face_matches_agrees_with_the_two_scans_it_replaced(
    conn: sqlite3.Connection, repo: SqliteRepository, store: SqliteMlStore, seed: int
) -> None:
    rng = random.Random(seed)
    a, b, other_model = assets(repo, 3)
    ids = store.replace_faces(a, M, random_faces(rng, 40))
    ids += store.replace_faces(b, M, [face((1.0, 0.0, 0.0))])  # another dimension
    store.replace_faces(other_model, "other", random_faces(rng, 10))
    people = [store.create_empty_person(None) for _ in range(4)]
    for face_id in rng.sample(ids, 20):
        store.assign_face(face_id, rng.choice(people))
    seen = set()
    for reach in (0.05, 0.3, 0.9, 2.0):
        for face_id in ids:
            count = conn.execute(_OLD_COUNT, (face_id, reach)).fetchone()[0]
            nearest = conn.execute(_OLD_NEAREST, (face_id, reach)).fetchone()
            expected = FaceMatches(count, None if nearest is None else nearest[0])
            assert store.face_matches(face_id, reach) == expected
            seen.add(expected)
    assert len(seen) > 20, "the inputs give many different answers"


def test_face_matches_is_one_scan_with_one_distance_per_other_face(
    conn: sqlite3.Connection, repo: SqliteRepository, store: SqliteMlStore
) -> None:
    """It was two scans, and the nearest person's distance was computed twice per match."""
    (a,) = assets(repo, 1)
    ids = store.replace_faces(a, M, [face(angle(d)) for d in (0, 5, 10, 15, 80, 90)])
    person = store.create_person(ids[2])
    store.assign_face(ids[1], person)
    distances: list[int] = []
    statements: list[str] = []

    def cosine(x: bytes, y: bytes) -> float:
        distances.append(1)
        return cosine_distance(from_blob(x), from_blob(y))

    conn.create_function("vec_distance_cosine", 2, cosine, deterministic=True)
    conn.set_trace_callback(statements.append)
    try:
        found = store.face_matches(ids[0], 1 - math.cos(math.radians(30)))
    finally:
        conn.set_trace_callback(None)
    assert found == FaceMatches(3, person)
    assert len(distances) == len(ids) - 1
    assert len([s for s in statements if "vec_distance_cosine" in s]) == 1


def test_deferred_faces_near_are_the_waiting_faces_within_reach_of_the_given_ones(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a, b) = assets(repo, 2)
    at = dict(
        zip((0, 20, 40, 100, 120, 200), store.replace_faces(a, M, [
            face(angle(d)) for d in (0, 20, 40, 100, 120, 200)
        ]), strict=True)
    )  # fmt: skip
    (elsewhere,) = store.replace_faces(b, "other", [face(angle(0))])
    for face_id in (*at.values(), elsewhere):
        store.mark_deferred(face_id)
    reach = 1 - math.cos(math.radians(30))
    assert store.deferred_faces_near(M, [at[20]], reach) == [at[0], at[40]], "not itself"
    assert store.deferred_faces_near(M, [at[20], at[120]], reach) == [at[0], at[40], at[100]]
    assert store.deferred_faces_near(M, [at[0], at[20]], reach) == [at[0], at[20], at[40]]
    assert store.deferred_faces_near(M, [at[200]], reach) == []
    assert store.deferred_faces_near(M, [], reach) == []
    assert store.deferred_faces_near(M, [elsewhere], reach) == [], "another model's face"
    store.assign_face(at[0], store.create_empty_person(None))  # placed: waits no longer
    store.mark_clustered(at[40])
    assert store.deferred_faces_near(M, [at[20]], reach) == []
    assert store.deferred_faces_near(M, [at[0]], reach) == [at[20]]


def test_deferred_faces_near_agree_with_plain_python_on_random_faces(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    rng = random.Random(3)
    (a,) = assets(repo, 1)
    faces = random_faces(rng, 60)
    ids = store.replace_faces(a, M, faces)
    vector = {i: f.embedding for i, f in zip(ids, faces, strict=True)}
    waiting = set(rng.sample(ids, 30))
    for face_id in waiting:
        store.mark_deferred(face_id)
    for reach in (0.05, 0.3, 0.9):
        given = rng.sample(ids, 8)
        expected = sorted(
            d for d in waiting
            if any(vector[d]) and any(
                g != d and any(vector[g]) and cosine_distance(vector[g], vector[d]) <= reach - 1e-6
                for g in given
            )
        )  # fmt: skip
        loose = sorted(
            d for d in waiting
            if any(vector[d]) and any(
                g != d and any(vector[g]) and cosine_distance(vector[g], vector[d]) <= reach + 1e-6
                for g in given
            )
        )  # fmt: skip
        found = store.deferred_faces_near(M, given, reach)
        assert set(expected) <= set(found) <= set(loose) and found == sorted(found)
        assert expected, "the inputs find something"


def test_face_changes_are_the_faces_added_placed_deferred_or_detected_again_since_the_marks_kept(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a, b) = assets(repo, 2)
    f1, f2, f3 = store.replace_faces(a, M, [face(angle(d)) for d in (0, 1, 2)])
    (elsewhere,) = store.replace_faces(b, "other", [face(angle(0))])
    first = store.face_changes(M)
    assert first.rule is None, "no pass has finished"
    assert set(first.marks) == {f1, f2, f3}
    assert store.face_changes(M) == first, "looking keeps nothing"
    store.keep_face_marks(M, "reach 0.5", first.marks)
    assert store.face_changes(M) == FaceChanges("reach 0.5", {})
    assert set(store.face_changes("other").marks) == {elsewhere}
    assert store.face_changes("other").rule is None

    def changed() -> set[int]:
        return set(store.face_changes(M).marks)

    store.mark_deferred(f1)
    assert changed() == {f1}
    store.assign_face(f2, store.create_empty_person(None))
    assert changed() == {f1, f2}
    (f4,) = store.replace_faces(b, M, [face(angle(3))])
    assert changed() == {f1, f2, f4}
    assert store.face_changes(M).rule == "reach 0.5"


def test_the_marks_kept_are_what_the_pass_saw_not_the_faces_as_they_are_when_it_ends(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    """Whatever happens to a face while a pass runs is a change for the next one."""
    (a,) = assets(repo, 1)
    f1, _ = store.replace_faces(a, M, [face(angle(0)), face(angle(1))])
    seen = store.face_changes(M).marks
    store.mark_deferred(f1)  # by the pass itself, or by a person meanwhile
    store.keep_face_marks(M, "reach 0.5", seen)
    assert set(store.face_changes(M).marks) == {f1}
    store.keep_face_marks(M, "reach 0.4", {})
    assert store.face_changes(M).rule == "reach 0.4", "the settings of the last pass"
    assert set(store.face_changes(M).marks) == {f1}


def test_keeping_marks_is_all_or_nothing(repo: SqliteRepository, store: SqliteMlStore) -> None:
    (a,) = assets(repo, 1)
    _, f2 = store.replace_faces(a, M, [face(angle(0)), face(angle(1))])
    seen = dict(store.face_changes(M).marks)
    with pytest.raises(sqlite3.Error):
        store.keep_face_marks(M, "reach 0.5", seen | {f2: (None, None, None, None)})
    assert store.face_changes(M) == FaceChanges(None, seen)


def test_the_mark_of_a_face_goes_with_it_and_its_id_starts_again_as_changed(
    repo: SqliteRepository, store: SqliteMlStore, conn: sqlite3.Connection
) -> None:
    (a, b) = assets(repo, 2)
    (f1,) = store.replace_faces(a, M, [face(angle(0))])
    (f2,) = store.replace_faces(b, M, [face(angle(90))])
    seen = store.face_changes(M).marks
    store.keep_face_marks(M, "reach 0.5", seen)
    conn.execute("DELETE FROM asset WHERE id = ?", (b,))  # a purged photo takes its faces along
    assert [r[0] for r in conn.execute("SELECT face_id FROM face_cluster_mark")] == [f1]
    assert store.face_changes(M).marks == {}
    assert store.replace_faces(a, M, [face(angle(0)), face(angle(90))]) == [f1, f2]
    assert set(store.face_changes(M).marks) == {f1, f2}, "the same ids, even the same vectors"
    store.replace_faces(a, M, [])
    store.keep_face_marks(M, "reach 0.5", seen)  # a pass ending after its faces went
    assert conn.execute("SELECT COUNT(*) FROM face_cluster_mark").fetchone()[0] == 0


def test_a_mark_left_behind_by_another_tool_does_not_hide_the_face_that_got_its_id(
    repo: SqliteRepository, store: SqliteMlStore, conn: sqlite3.Connection
) -> None:
    """A connection without foreign keys (the sqlite3 shell) deletes a face and not its mark."""
    (a,) = assets(repo, 1)
    (f1,) = store.replace_faces(a, M, [face(angle(0))])
    store.mark_deferred(f1)
    store.keep_face_marks(M, "reach 0.5", store.face_changes(M).marks)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM face")
    conn.execute("PRAGMA foreign_keys = ON")
    assert conn.execute("SELECT COUNT(*) FROM face_cluster_mark").fetchone()[0] == 1
    assert store.face_changes(M).marks == {}
    assert store.replace_faces(a, M, [face(angle(90))]) == [f1]
    store.mark_deferred(f1)
    assert set(store.face_changes(M).marks) == {f1}


def test_cluster_queue_by_state_and_asset(repo: SqliteRepository, store: SqliteMlStore) -> None:
    (a, b) = assets(repo, 2)
    f1, f2 = store.replace_faces(a, M, [face(angle(0)), face(angle(1))])
    (f3,) = store.replace_faces(b, M, [face(angle(2))])
    assert store.faces_to_cluster(M, deferred=False) == [f1, f2, f3]
    assert store.faces_to_cluster(M, deferred=False, asset_id=b) == [f3]
    store.mark_deferred(f1)
    store.mark_clustered(f2)
    assert store.faces_to_cluster(M, deferred=False) == [f3]
    assert store.faces_to_cluster(M, deferred=True) == [f1]


# --- people, visibility-scoped ---------------------------------------------------------------


def test_people_only_count_faces_in_visible_assets(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a, b, c) = assets(repo, 3)
    (fa,) = store.replace_faces(a, M, [face(angle(0), score=0.99)])
    (fb,) = store.replace_faces(b, M, [face(angle(1), score=0.7)])
    (fc,) = store.replace_faces(c, M, [face(angle(90))])
    lea = store.create_person(fa)
    store.assign_face(fb, lea)
    tom = store.create_person(fc)
    store.rename_person(lea, "Léa")

    (only,) = store.list_persons(visible={b})
    assert (only.id, only.name, only.face_count, only.asset_count) == (lea, "Léa", 1, 1)
    assert only.cover_face is not None and only.cover_face.id == fb  # cover a is hidden
    full = store.get_person(lea, visible={a, b, c})
    assert full is not None and full.cover_face is not None and full.cover_face.id == fa
    assert store.get_person(tom, visible={a, b}) is None
    assert [p.id for p in store.list_persons(visible={a, b, c})] == [lea, tom]
    assert store.person_asset_ids(lea, visible={b, c}) == [b]


def test_merge_moves_faces_keeps_a_name_and_removes_sources(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a, b) = assets(repo, 2)
    (fa,) = store.replace_faces(a, M, [face(angle(0))])
    (fb,) = store.replace_faces(b, M, [face(angle(1))])
    target = store.create_person(fa)
    source = store.create_person(fb)
    store.rename_person(source, "Tom")
    store.merge_persons(target, [source])
    person = store.get_person(target, visible={a, b})
    assert person is not None and person.name == "Tom" and person.face_count == 2
    assert store.get_person(source, visible={a, b}) is None


def test_move_faces_is_sticky_and_empty_people_are_removed(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a,) = assets(repo, 1)
    f1, f2 = store.replace_faces(a, M, [face(angle(0)), face(angle(1))])
    first = store.create_person(f1)
    store.assign_face(f2, first)
    other = store.create_empty_person("Split")
    store.move_faces([f1, f2], other)
    assert store.delete_empty_persons() == 1
    assert store.faces_to_cluster(M, deferred=False) == []
    moved = store.get_face(f1)
    assert moved is not None and moved.person_id == other


# --- tags --------------------------------------------------------------------------------------


def test_model_tags_are_replaced_but_user_tags_survive(
    repo: SqliteRepository, store: SqliteMlStore, conn: sqlite3.Connection
) -> None:
    (a,) = assets(repo, 1)
    store.replace_model_tags(a, M, [TagScore("beach", 0.2)], False)
    conn.execute("INSERT INTO tag (name, kind) VALUES ('sunset', 'manual')")
    conn.execute(
        "INSERT INTO asset_tag (asset_id, tag_id, score, by) "
        "SELECT ?, id, NULL, 'user' FROM tag WHERE name = 'sunset'",
        (a,),
    )
    store.replace_model_tags(a, M, [TagScore("snow", 0.05), TagScore("sunset", 0.3)], True)
    assert [t.name for t in store.tags_of(a)] == ["sunset", "snow"]
    assert store.is_screen_or_document(a) is True


def test_screen_flag_is_unknown_before_tagging(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a,) = assets(repo, 1)
    assert store.is_screen_or_document(a) is None
    assert store.tags_of(a) == []


def test_assets_with_a_tag_within_the_visible_set(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    (a, b, c) = assets(repo, 3)
    for asset in (a, b, c):
        store.replace_model_tags(asset, M, [TagScore("Beach", 0.2)], asset == c)
    assert store.asset_ids_with_tag("beach", visible={a, c}) == [a, c]
    assert store.asset_ids_with_tag("snow", visible={a, b, c}) == []
    assert store.screen_or_document_ids(visible={a, b, c}) == [c]


# --- the viewer instead of the list of every photo they may see ------------------------------


def indexed_random_library(seed: int) -> tuple[SqliteRepository, SqliteMlStore, list[int]]:
    """60 photos with owners, access lists, albums, private marks and trash (the library of
    the visibility rule's own test), plus hidden marks, photos held for review, and on every
    photo: an embedding, faces of four people, tags."""
    rng = random.Random(seed)
    repo = _random_library(seed)
    conn = repo._conn
    store = SqliteMlStore(repo._db)
    photos = list(range(1, 61))
    for user in range(1, len(ROLES) + 1):
        for asset in rng.sample(photos, 6):
            conn.execute(
                "INSERT INTO user_asset (user_id, asset_id, favourite, hidden) VALUES (?, ?, 0, 1)",
                (user, asset),
            )
    for asset in rng.sample(photos, 5):
        conn.execute("UPDATE asset SET held_reason = 'lookalike' WHERE id = ?", (asset,))
    people = [store.create_empty_person(name) for name in ("Lea", None, "Tom", None)]
    for asset in photos:
        store.save_clip(asset, M, tuple(rng.gauss(0, 1) for _ in range(4)))
        vectors = [tuple(rng.gauss(0, 1) for _ in range(4)) for _ in range(rng.randint(0, 2))]
        for face_id in store.replace_faces(asset, M, [face(v, rng.random()) for v in vectors]):
            if rng.random() < 0.8:
                store.assign_face(face_id, rng.choice(people))
        tags = [TagScore(name, 0.2) for name in ("beach", "snow") if rng.random() < 0.4]
        store.replace_model_tags(asset, M, tags, screen_or_document=rng.random() < 0.3)
    return repo, store, people


@pytest.mark.parametrize("seed", range(8))
def test_a_viewer_gets_what_the_list_of_every_photo_they_may_see_gave(seed: int) -> None:
    repo, store, people = indexed_random_library(seed)
    rng = random.Random(seed)
    seen_by_someone = 0
    for user, role in enumerate(ROLES, start=1):
        viewer = Viewer(user, role)
        ids = repo.visible_asset_ids(viewer)  # what the routes handed over before
        seen_by_someone += len(ids)
        assert store.seen(range(1, 70), viewer) == set(ids)
        assert store.list_persons(viewer) == store.list_persons(ids)
        for person in people:
            assert store.get_person(person, viewer) == store.get_person(person, ids)
            theirs = set(store.person_asset_ids(person, ids))
            assert store.person_asset_ids(person, viewer) == [i for i in ids if i in theirs]
        query = tuple(rng.gauss(0, 1) for _ in range(4))
        assert store.nearest_assets(query, M, viewer, 10) == store.nearest_assets(query, M, ids, 10)
        for asset in ids[:5]:
            others = set(ids) - {asset}
            expected = store.nearest_assets(query, M, others, 10) if others else []
            assert store.nearest_assets(query, M, viewer, 10, leave_out=asset) == expected
        assert store.asset_ids_with_tag("Beach", viewer) == store.asset_ids_with_tag("Beach", ids)
        assert store.screen_or_document_ids(viewer) == store.screen_or_document_ids(ids)
    assert seen_by_someone > 60, "the viewers do see photos, and not all the same ones"


def test_seen_with_a_list_of_photos_is_what_is_on_the_list(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    a, b, c = assets(repo, 3)
    assert store.seen([a, b, 99], [b, c]) == {b}
    assert store.seen([], [a]) == set()


def test_a_persons_photos_come_newest_first_like_the_timeline(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    days = (3, 9, 9, 1)
    ids = [repo.add_asset(new_asset(n, datetime(2020, 1, d)), NOW) for n, d in enumerate(days, 1)]
    person = store.create_empty_person("Lea")
    for asset in ids:
        (face_id,) = store.replace_faces(asset, M, [face(angle(0))])
        store.assign_face(face_id, person)
    a, b, c, d = ids
    assert store.person_asset_ids(person, ids) == [c, b, a, d]


def test_one_persons_page_for_a_viewer_reads_that_persons_faces_not_the_library() -> None:
    """It was: list every photo the viewer may see, copy the ids into a temp table, join."""
    repo, store, people = indexed_random_library(1)
    conn = repo._conn
    statements: list[str] = []
    viewers = (Viewer(1, Role.ADMIN), Viewer(2, Role.MEMBER), Viewer(5, Role.GUEST))
    conn.set_trace_callback(statements.append)
    try:
        for viewer in viewers:
            store.get_person(people[0], viewer)
            store.person_asset_ids(people[0], viewer)
        one_person = [s for s in statements if s.startswith(("SELECT", "WITH"))]
        for viewer in viewers:
            store.list_persons(viewer)
    finally:
        conn.set_trace_callback(None)
    assert [s for s in statements if "ml_candidates" in s] == []
    assert len(one_person) >= 6
    for sql in one_person:
        plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql))
        by_person = "USING INDEX face_by_person (person_id=?)" in plan
        cover = "SEARCH f USING INTEGER PRIMARY KEY (rowid=?)"
        # the cover face, with (issue 53) the photo it is on: both read by their id
        with_its_photo = f"{cover} | SEARCH a USING INTEGER PRIMARY KEY (rowid=?)"
        assert by_person or plan in (cover, with_its_photo), plan
        # no walk over a whole table, nor over every photo that is not in the trash
        assert not re.search(r"SCAN (?!\(subquery)", plan) and "(trashed_at=?)" not in plan, plan


def test_task_counts_summarise_the_status_of_every_task(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    a, b, c = assets(repo, 3)
    store.set_task_status(a, "embed_clip", "m", "done")
    store.set_task_status(b, "embed_clip", "m", "done")
    store.set_task_status(c, "embed_clip", "m", "model_missing", "run just models")
    store.set_task_status(a, "detect_faces", "f", "failed", "broken")
    assert store.task_counts() == {
        "detect_faces": {"failed": 1},
        "embed_clip": {"done": 2, "model_missing": 1},
    }
