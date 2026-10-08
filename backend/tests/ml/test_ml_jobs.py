"""Job handlers: embed_clip, detect_faces, cluster_faces, auto_tag; planning and backfill."""

import math
import random
import sqlite3
from pathlib import Path

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.ml_jobs import (
    AUTO_TAG,
    CLUSTER_FACES,
    DETECT_FACES,
    EMBED_CLIP,
    AutoTag,
    ClusterFaces,
    DetectFaces,
    EmbedClip,
    MlJobPlanner,
    TaskStatus,
)
from photo_assistant.domain.clustering import ClusterParams, cluster
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagParams, TagSpec
from photo_assistant.domain.vectors import Vector
from photo_assistant.ports import RenderedImage
from tests.factories import NOW, new_asset
from tests.ml.fakes import FakeClip, FakeFaces, FakeLibrary


@pytest.fixture
def conn() -> sqlite3.Connection:
    return open_database(":memory:")


@pytest.fixture
def repo(conn: sqlite3.Connection) -> SqliteRepository:
    return SqliteRepository(conn)


@pytest.fixture
def store(conn: sqlite3.Connection) -> SqliteMlStore:
    return SqliteMlStore(conn)


@pytest.fixture
def library(tmp_path: Path) -> FakeLibrary:
    return FakeLibrary(tmp_path)


def add(repo: SqliteRepository, n: int, image: str | None = None) -> int:
    asset_id = repo.add_asset(new_asset(n), NOW)
    if image:
        repo.set_thumbnail(asset_id, RenderedImage(f"derived/thumb/{image}", 64, 48))
    return asset_id


def queued(repo: SqliteRepository) -> list[tuple[str, object]]:
    return [(j["kind"], j["payload"]) for j in repo.list_jobs("queued")]


# --- embed_clip ---------------------------------------------------------------------------------


def test_embed_clip_stores_a_vector_from_the_best_rendition(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "a1.webp")
    repo.set_preview(asset, RenderedImage("derived/preview/p1.webp", 2048, 1536))
    clip = FakeClip()
    clip.images["p1.webp"] = (0.0, 1.0, 0.0, 0.0)
    EmbedClip(repo, library, store, clip)({"asset_id": asset})
    assert store.clip_vector(asset, clip.name) == pytest.approx((0.0, 1.0, 0.0, 0.0))
    assert store.task_status(asset, EMBED_CLIP, clip.name) == TaskStatus.DONE


def test_embed_clip_is_idempotent(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "a1.webp")
    clip = FakeClip()
    handler = EmbedClip(repo, library, store, clip)
    handler({"asset_id": asset})
    handler({"asset_id": asset})
    assert clip.calls == 1


def test_missing_model_is_recorded_not_failed(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "a1.webp")
    clip = FakeClip(available=False)
    EmbedClip(repo, library, store, clip)({"asset_id": asset})
    assert store.task_status(asset, EMBED_CLIP, clip.name) == TaskStatus.MODEL_MISSING
    clip.available = True  # after `just models`, the backfill re-runs it
    EmbedClip(repo, library, store, clip)({"asset_id": asset})
    assert store.task_status(asset, EMBED_CLIP, clip.name) == TaskStatus.DONE


def test_undecodable_image_is_recorded_as_unreadable(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "broken.webp")
    EmbedClip(repo, library, store, FakeClip())({"asset_id": asset})
    assert store.task_status(asset, EMBED_CLIP, "clip-fake") == TaskStatus.UNREADABLE


def test_a_deleted_asset_is_nothing_to_do(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    """A photo purged while its job waited: the job ends quietly and records nothing."""
    clip = FakeClip()
    EmbedClip(repo, library, store, clip)({"asset_id": 999})
    assert store.task_status(999, EMBED_CLIP, clip.name) is None
    assert store.clip_vector(999, clip.name) is None
    assert store.task_counts() == {}


def test_payload_must_name_an_asset(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    with pytest.raises(ValueError, match="asset_id"):
        EmbedClip(repo, library, store, FakeClip())({})


# --- detect_faces + cluster_faces ----------------------------------------------------------------


def angle(deg: float) -> Vector:
    return (math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0)


def test_detect_faces_stores_faces_and_queues_clustering(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "group.webp")
    empty = add(repo, 2, "landscape.webp")
    faces = FakeFaces()
    faces.faces["group.webp"] = [angle(0), angle(90)]
    handler = DetectFaces(repo, library, store, faces)
    handler({"asset_id": asset})
    handler({"asset_id": empty})
    handler({"asset_id": asset})  # idempotent
    assert len(store.faces_of_asset(asset)) == 2
    assert store.task_status(empty, DETECT_FACES, faces.name) == TaskStatus.DONE
    assert queued(repo) == [(CLUSTER_FACES, {"asset_id": asset})]
    assert faces.calls == 2


def test_detect_faces_with_missing_model(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "a.webp")
    DetectFaces(repo, library, store, FakeFaces(available=False))({"asset_id": asset})
    assert store.task_status(asset, DETECT_FACES, "faces-fake") == TaskStatus.MODEL_MISSING
    assert queued(repo) == []


def blob(centre: int, n: int, rng: random.Random) -> list[Vector]:
    out = []
    for _ in range(n):
        v = [rng.uniform(-0.05, 0.05) for _ in range(6)]
        v[centre] += 1.0
        out.append(tuple(v))
    return out


def partition(labels: dict[int, int | None]) -> set[frozenset[int]]:
    groups: dict[int, set[int]] = {}
    for face, person in labels.items():
        if person is not None:
            groups.setdefault(person, set()).add(face)
    return {frozenset(g) for g in groups.values()}


def test_clustering_through_sqlite_vec_matches_the_reference_algorithm(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    rng = random.Random(7)
    noise = [tuple(rng.gauss(0, 1) for _ in range(6)) for _ in range(6)]
    vectors = blob(0, 5, rng) + blob(1, 4, rng) + blob(2, 2, rng) + noise
    rng.shuffle(vectors)
    asset = add(repo, 1)
    ids = store.replace_faces(
        asset, "m", [Face(BoundingBox(0, 0, 1, 1), 0.9, (), v) for v in vectors]
    )
    params = ClusterParams(max_distance=0.4, min_faces=3)
    ClusterFaces(store, "m", params)({})
    got = {f: store.get_face(f).person_id for f in ids}  # type: ignore[union-attr]
    expected = cluster(dict(zip(ids, vectors, strict=True)), params)
    assert partition(got) == partition(expected)
    assert len(partition(got)) >= 2


def test_per_asset_clustering_defers_then_the_global_pass_resolves(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    def put(asset: int, degrees: list[float]) -> list[int]:
        faces = [Face(BoundingBox(0, 0, 1, 1), 0.9, (), angle(d)) for d in degrees]
        return store.replace_faces(asset, "m", faces)

    a, b = add(repo, 1), add(repo, 2)
    (lonely,) = put(a, [75])  # one neighbour only, once the others exist
    core = put(b, [0, 10, 20])
    job = ClusterFaces(store, "m", ClusterParams(0.5, 3))
    job({"asset_id": a})
    assert store.get_face(lonely).person_id is None  # type: ignore[union-attr]
    job({"asset_id": b})
    person = store.get_face(core[0]).person_id  # type: ignore[union-attr]
    assert person is not None
    job({})  # the global pass revisits deferred faces
    assert store.get_face(lonely).person_id == person  # type: ignore[union-attr]


def test_user_placed_faces_are_never_reclustered(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    asset = add(repo, 1)
    ids = store.replace_faces(
        asset, "m", [Face(BoundingBox(0, 0, 1, 1), 0.9, (), angle(d)) for d in (0, 5, 10)]
    )
    chosen = store.create_empty_person("Mine")
    store.move_faces([ids[0]], chosen)
    ClusterFaces(store, "m", ClusterParams(0.5, 3))({})
    assert store.get_face(ids[0]).person_id == chosen  # type: ignore[union-attr]
    assert store.get_face(ids[1]).person_id == chosen  # type: ignore[union-attr]


# --- auto_tag ------------------------------------------------------------------------------------

VOCAB = (
    TagSpec("beach", ("beach",)),
    TagSpec("screenshot", ("screenshot",), screen_or_document=True),
)


def tag_clip() -> FakeClip:
    clip = FakeClip()
    clip.texts |= {"beach": (1.0, 0.0, 0.0, 0.0), "screenshot": (0.0, 1.0, 0.0, 0.0)}
    clip.images |= {"sea.webp": (1.0, 0.0, 0.0, 0.2), "screen.webp": (0.0, 1.0, 0.0, 0.2)}
    return clip  # background prompts fall back to the last axis


def test_auto_tag_embeds_if_needed_then_tags_and_flags(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    sea, screen = add(repo, 1, "sea.webp"), add(repo, 2, "screen.webp")
    clip = tag_clip()
    handler = AutoTag(EmbedClip(repo, library, store, clip), store, clip, TagParams(0.1), VOCAB)
    handler({"asset_id": sea})
    handler({"asset_id": screen})
    assert [t.name for t in store.tags_of(sea)] == ["beach"]
    assert store.is_screen_or_document(sea) is False
    assert [t.name for t in store.tags_of(screen)] == ["screenshot"]
    assert store.is_screen_or_document(screen) is True
    calls = clip.calls
    handler({"asset_id": sea})  # done → nothing re-run
    assert clip.calls == calls
    assert store.task_status(sea, EMBED_CLIP, clip.name) == TaskStatus.DONE


def test_auto_tag_hands_each_photos_tags_on_for_the_review_check(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    sea, screen = add(repo, 1, "sea.webp"), add(repo, 2, "screen.webp")
    clip = tag_clip()
    seen: dict[int, list[str]] = {}
    handler = AutoTag(
        EmbedClip(repo, library, store, clip),
        store,
        clip,
        TagParams(0.1),
        VOCAB,
        on_tags=lambda asset_id, tags: seen.update({asset_id: [t.name for t in tags]}),
    )
    handler({"asset_id": sea})
    handler({"asset_id": screen})
    handler({"asset_id": screen})  # done: not handed on twice
    assert seen == {sea: ["beach"], screen: ["screenshot"]}


def test_auto_tag_with_missing_model(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "sea.webp")
    clip = FakeClip(available=False)
    AutoTag(EmbedClip(repo, library, store, clip), store, clip, TagParams(), VOCAB)(
        {"asset_id": asset}
    )
    assert store.task_status(asset, AUTO_TAG, clip.name) == TaskStatus.MODEL_MISSING


def test_auto_tag_when_only_the_text_model_is_missing(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    asset = add(repo, 1, "sea.webp")
    clip, text = FakeClip(), FakeClip(available=False)
    AutoTag(EmbedClip(repo, library, store, clip), store, text, TagParams(), VOCAB)(
        {"asset_id": asset}
    )
    assert store.task_status(asset, AUTO_TAG, clip.name) == TaskStatus.MODEL_MISSING
    assert store.task_status(asset, EMBED_CLIP, clip.name) == TaskStatus.DONE


def test_auto_tag_of_a_missing_asset(
    repo: SqliteRepository, store: SqliteMlStore, library: FakeLibrary
) -> None:
    clip = FakeClip()
    AutoTag(EmbedClip(repo, library, store, clip), store, clip, TagParams(), VOCAB)(
        {"asset_id": 42}
    )
    assert store.task_status(42, AUTO_TAG, clip.name) is None


# --- planning ------------------------------------------------------------------------------


def test_planner_queues_ml_jobs_after_the_preview(repo: SqliteRepository) -> None:
    ran: list[object] = []
    planner = MlJobPlanner(repo, {EMBED_CLIP: "c", DETECT_FACES: "f", AUTO_TAG: "c"})
    wrapped = planner.after(lambda payload: ran.append(payload["asset_id"]))
    wrapped({"asset_id": 5})
    assert ran == [5]
    assert queued(repo) == [
        (EMBED_CLIP, {"asset_id": 5}),
        (DETECT_FACES, {"asset_id": 5}),
        (AUTO_TAG, {"asset_id": 5}),
    ]


def test_planner_skips_disabled_tasks(repo: SqliteRepository) -> None:
    MlJobPlanner(repo, {EMBED_CLIP: "c"}).for_asset(3)
    assert queued(repo) == [(EMBED_CLIP, {"asset_id": 3})]


def test_backfill_queues_only_unfinished_work_then_one_global_clustering(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    done, missing, fresh = add(repo, 1), add(repo, 2), add(repo, 3)
    for task in (EMBED_CLIP, AUTO_TAG):
        store.set_task_status(done, task, "c", TaskStatus.DONE)
    store.set_task_status(done, DETECT_FACES, "f", TaskStatus.DONE)
    store.set_task_status(missing, EMBED_CLIP, "c", TaskStatus.MODEL_MISSING)
    planner = MlJobPlanner(repo, {EMBED_CLIP: "c", DETECT_FACES: "f", AUTO_TAG: "c"})
    count = planner.backfill(store, page_size=2)
    jobs = queued(repo)
    assert count == len(jobs) - 1 == 6
    assert (EMBED_CLIP, {"asset_id": missing}) in jobs
    assert (DETECT_FACES, {"asset_id": fresh}) in jobs
    assert all(payload != {"asset_id": done} for _, payload in jobs)
    assert jobs[-1] == (CLUSTER_FACES, {})


def test_planner_queues_nothing_for_a_model_that_is_not_installed(
    repo: SqliteRepository,
) -> None:
    """C31: without model files, ML jobs would only fail; don't queue them (just ml-backfill
    queues the work once the models are there)."""
    installed = {EMBED_CLIP, AUTO_TAG}
    planner = MlJobPlanner(
        repo, {EMBED_CLIP: "c", DETECT_FACES: "f", AUTO_TAG: "c"}, ready=installed.__contains__
    )
    planner.for_asset(4)
    assert queued(repo) == [(EMBED_CLIP, {"asset_id": 4}), (AUTO_TAG, {"asset_id": 4})]
