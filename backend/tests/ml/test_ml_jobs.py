"""Job handlers: embed_clip, detect_faces, cluster_faces, auto_tag; planning and backfill."""

import math
import random
import sqlite3
from collections.abc import Callable, Sequence
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
from photo_assistant.domain.clustering import Action, ClusterParams, cluster, decide
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagParams, TagSpec
from photo_assistant.domain.vectors import Vector, cosine_distance
from photo_assistant.ports import RenderedImage
from photo_assistant.ports.ml import FaceMatches, MlStore
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


# --- the global pass looks again only at deferred faces something changed around ---------------


class EveryDeferredFaceEveryPass:
    """The global pass as it was, the oracle: each one steps every deferred face again."""

    def __init__(self, store: MlStore, model: str, params: ClusterParams) -> None:
        self._store, self._model, self._params = store, model, params

    def __call__(self, payload: dict[str, object]) -> None:
        asset_id = payload.get("asset_id")
        assert asset_id is None or isinstance(asset_id, int)
        for face_id in self._store.faces_to_cluster(self._model, deferred=False, asset_id=asset_id):
            self._step(face_id, deferred=False)
        if asset_id is None:
            for face_id in self._store.faces_to_cluster(self._model, deferred=True):
                self._step(face_id, deferred=True)

    def _step(self, face_id: int, *, deferred: bool) -> None:
        found = self._store.face_matches(face_id, self._params.max_distance)
        decision = decide(found.count, found.person_id, self._params, deferred=deferred)
        if decision.action is Action.ASSIGN and decision.person_id is not None:
            self._store.assign_face(face_id, decision.person_id)
        elif decision.action is Action.NEW_PERSON:
            self._store.create_person(face_id)
        elif not deferred:
            self._store.mark_deferred(face_id)


class CountingStore(SqliteMlStore):
    """The real store, counting the neighbour scans (one face against every other face)."""

    scans = 0
    fail_at: int | None = None

    def face_matches(self, face_id: int, max_distance: float) -> FaceMatches:
        self.scans += 1
        if self.scans == self.fail_at:
            raise sqlite3.OperationalError("disk I/O error")
        return super().face_matches(face_id, max_distance)


class World:
    """One library; ``job`` is the handler under test, or the oracle."""

    PARAMS = ClusterParams(max_distance=0.4, min_faces=3)

    def __init__(self, incremental: bool) -> None:
        self.conn = open_database(":memory:")
        self.repo = SqliteRepository(self.conn)
        self.store = CountingStore(self.conn)
        self.incremental = incremental
        self.assets = 0
        self.restart()

    def restart(self) -> None:
        kind = ClusterFaces if self.incremental else EveryDeferredFaceEveryPass
        self.job = kind(self.store, "m", self.PARAMS)

    def photo(self, vectors: Sequence[Vector]) -> int:
        self.assets += 1
        return self.detect(self.repo.add_asset(new_asset(self.assets), NOW), vectors)

    def detect(self, asset: int, vectors: Sequence[Vector]) -> int:
        faces = [Face(BoundingBox(0, 0, 1, 1), 0.9, (), v) for v in vectors]
        self.store.replace_faces(asset, "m", faces)
        return asset

    def people(self) -> dict[int, int | None]:
        rows = self.conn.execute("SELECT id, person_id FROM face ORDER BY id").fetchall()
        return {r[0]: r[1] for r in rows}

    def unplaced(self) -> list[int]:
        return [f for f, person in self.people().items() if person is None]

    def distance_statements(self, run: Callable[[], object]) -> int:
        statements: list[str] = []
        self.conn.set_trace_callback(statements.append)
        try:
            run()
        finally:
            self.conn.set_trace_callback(None)
        return len([s for s in statements if "vec_distance_cosine" in s])


def some_faces(rng: random.Random, centres: Sequence[Vector]) -> list[Vector]:
    return [
        tuple(c + rng.uniform(-0.45, 0.45) for c in rng.choice(centres))
        if rng.random() < 0.7 else tuple(rng.gauss(0, 1) for _ in range(6))
        for _ in range(rng.randint(1, 3))
    ]  # fmt: skip


def a_day(rng: random.Random, centres: Sequence[Vector], worlds: Sequence[World]) -> None:
    """New photos (some clustered at once, as the detect job does), then one thing a person
    does on the People screen or a photo detected again; the same in every world."""
    for _ in range(rng.randint(0, 5)):
        vectors, clustered_now = some_faces(rng, centres), rng.random() < 0.5
        for world in worlds:
            asset = world.photo(vectors)
            if clustered_now:
                world.job({"asset_id": asset})
    first = worlds[0]
    unplaced = first.unplaced()
    persons = sorted({p for p in first.people().values() if p is not None})
    roll, face = rng.random(), rng.choice(unplaced) if unplaced else None
    her = rng.choice(persons) if persons else None
    again, new_faces = rng.randint(1, max(1, first.assets)), some_faces(rng, centres)
    for world in worlds:
        if roll < 0.4 and face is not None:
            # "this is her" or, without anyone to choose, "this is someone new"
            someone = her if roll < 0.25 and her is not None else None
            world.store.move_faces([face], someone or world.store.create_empty_person("New"))
        elif roll < 0.5 and len(persons) > 1:
            world.store.merge_persons(persons[0], [persons[-1]])
        elif roll < 0.65 and first.assets:
            world.detect(again, new_faces)


@pytest.mark.parametrize("seed", range(12))
def test_the_global_pass_finds_the_same_people_as_stepping_every_deferred_face_every_time(
    seed: int,
) -> None:
    rng = random.Random(seed)
    centres = [tuple(rng.gauss(0, 1) for _ in range(6)) for _ in range(5)]
    oracle, incremental = World(incremental=False), World(incremental=True)
    for _ in range(20):  # mostly strangers, who stay deferred
        vector = tuple(rng.gauss(0, 1) for _ in range(6))
        oracle.photo([vector])
        incremental.photo([vector])
    late = 0
    for day in range(14):
        a_day(rng, centres, [oracle, incremental])
        assert incremental.people() == oracle.people(), f"before the pass of day {day}"
        if day == 8:
            incremental.restart()  # a server restart forgets what the last pass saw
        placed_before = set(oracle.people()) - set(oracle.unplaced())
        was_deferred = set(oracle.store.faces_to_cluster("m", deferred=True))
        oracle.job({})
        incremental.job({})
        assert incremental.people() == oracle.people(), f"day {day}"
        late += len(was_deferred - set(oracle.unplaced()) - placed_before)
    assert late >= 3, "faces that had been deferred did find their person in a later pass"
    assert len({p for p in oracle.people().values() if p is not None}) >= 2
    assert incremental.store.scans < oracle.store.scans


def strangers(n: int, seed: int = 1) -> list[Vector]:
    """Pairwise far apart: nobody matches anybody."""
    rng = random.Random(seed)
    found: list[Vector] = []
    while len(found) < n:
        v = tuple(rng.gauss(0, 1) for _ in range(40))
        if all(cosine_distance(v, other) > 0.6 for other in found):
            found.append(v)
    return found


def test_a_global_pass_with_nothing_new_since_the_last_one_scans_no_face() -> None:
    """It was two scans of every face for each stranger, every night and at every start."""
    world = World(incremental=True)
    for v in strangers(30):
        world.photo([v])
    world.job({})
    assert len(world.unplaced()) == 30
    world.store.scans = 0
    assert world.distance_statements(lambda: world.job({})) == 0
    assert world.store.scans == 0


def test_a_new_face_is_held_against_the_deferred_faces_not_each_of_them_against_everyone() -> None:
    world = World(incremental=True)
    vectors = strangers(31)
    for v in vectors[:30]:
        world.photo([v])
    world.job({})
    world.photo([vectors[30]])
    world.store.scans = 0
    # the new face as a new face, who waits near it, the new face again as a deferred one
    assert world.distance_statements(lambda: world.job({})) == 3
    assert world.store.scans == 2, "the 30 others are not stepped"


def turned(*degrees: float) -> list[Vector]:
    return [angle(d) for d in degrees]


HALF = ClusterParams(max_distance=1 - math.cos(math.radians(30)), min_faces=3)  # 30 degrees


def test_a_deferred_face_joins_the_person_that_later_photos_put_next_to_it() -> None:
    world = World(incremental=True)
    world.job = ClusterFaces(world.store, "m", HALF)
    world.photo(turned(50))
    world.job({})
    (lonely,) = world.unplaced()
    world.job({"asset_id": world.photo(turned(0, 10, 20))})
    assert world.people()[lonely] is None
    world.job({})
    assert world.people()[lonely] is not None


def test_a_deferred_face_follows_a_face_next_to_it_that_a_person_placed() -> None:
    world = World(incremental=True)
    world.job = ClusterFaces(world.store, "m", HALF)
    world.photo(turned(0, 20))
    world.job({})
    waiting, placed = world.unplaced()
    her = world.store.create_empty_person("Lea")
    world.store.move_faces([placed], her)
    world.job({})
    assert world.people()[waiting] == her


@pytest.mark.parametrize("first, same_pass", [(45, True), (70, False)])
def test_a_face_placed_in_a_pass_takes_later_deferred_faces_along_and_earlier_ones_next_time(
    first: int, same_pass: bool
) -> None:
    """As when every deferred face is stepped in id order: 70 reaches the person only through
    45, so it joins in the same pass when it comes after 45, else in the pass after."""
    world = World(incremental=True)
    world.job = ClusterFaces(world.store, "m", HALF)
    world.photo(turned(first))
    world.photo(turned(115 - first))
    world.job({})
    assert len(world.unplaced()) == 2
    at = dict(zip((first, 115 - first), world.unplaced(), strict=True))
    world.job({"asset_id": world.photo(turned(0, 10, 20))})
    world.job({})
    people = world.people()
    assert people[at[45]] is not None
    assert people[at[70]] == (people[at[45]] if same_pass else None)
    world.job({})
    assert world.people()[at[70]] == people[at[45]]


def test_a_pass_that_failed_half_way_is_followed_by_a_pass_over_every_deferred_face() -> None:
    oracle, world = World(incremental=False), World(incremental=True)
    for each in (oracle, world):
        each.job = type(each.job)(each.store, "m", HALF)
        each.photo(turned(50))
        each.photo(turned(230))
        each.job({})
        each.job({"asset_id": each.photo(turned(0, 10, 20))})
        each.job({"asset_id": each.photo(turned(180, 190, 200))})
    world.store.fail_at = world.store.scans + 2  # at the second deferred face of this pass
    with pytest.raises(sqlite3.OperationalError):
        world.job({})
    assert len(world.unplaced()) == 1
    oracle.job({})
    world.job({})
    assert world.people() == oracle.people()
    assert world.unplaced() == []


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


def test_running_the_backfill_twice_does_not_double_the_jobs(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    add(repo, 1), add(repo, 2)
    planner = MlJobPlanner(repo, {EMBED_CLIP: "c", DETECT_FACES: "f"})
    assert planner.backfill(store) == 4
    first = queued(repo)
    assert planner.backfill(store) == 0, "everything is already waiting"
    assert queued(repo) == first and first.count((CLUSTER_FACES, {})) == 1


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
