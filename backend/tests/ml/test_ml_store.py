"""SqliteMlStore against real SQLite + sqlite-vec (in memory)."""

import math
import sqlite3
from pathlib import Path

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore, from_blob, open_ml_store, to_blob
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from photo_assistant.domain.vectors import Vector
from tests.factories import NOW, new_asset

M = "test-model"


@pytest.fixture
def conn() -> sqlite3.Connection:
    return open_database(":memory:")


@pytest.fixture
def repo(conn: sqlite3.Connection) -> SqliteRepository:
    return SqliteRepository(conn)


@pytest.fixture
def store(conn: sqlite3.Connection) -> SqliteMlStore:
    return SqliteMlStore(conn)


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


def test_open_ml_store_on_a_file_migrates_and_loads_sqlite_vec(tmp_path: Path) -> None:
    store = open_ml_store(tmp_path / "library.db")
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
    assert store.count_face_matches(good, 2.0, limit=10) == 0
    assert store.count_face_matches(zero, 2.0, limit=10) == 0
    assert store.nearest_person(zero, 2.0) is None


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
        pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3), pytest.approx(0.4)
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
    assert store.count_face_matches(f1, reach, limit=10) == 1
    assert store.count_face_matches(f3, reach, limit=10) == 0
    assert store.nearest_person(f1, reach) is None
    person = store.create_person(f2)
    assert store.nearest_person(f1, reach) == person
    assert store.get_face(f2).person_id == person  # type: ignore[union-attr]


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
