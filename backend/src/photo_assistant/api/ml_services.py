"""Composition for local ML: builds adapters and use cases from settings.

Meant to be called from ``api/services.py`` (see docs/wiring/ml.md): it returns the job
handlers to merge into the Worker and the use cases the routes need. Nothing here loads a
model — that happens on first use, so the app starts fine without any model files.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from photo_assistant.adapters.faces_insightface import InsightFaceAnalyzer
from photo_assistant.adapters.faces_opencv import YuNetSFaceAnalyzer
from photo_assistant.adapters.ml_store import SqliteMlStore, open_ml_store
from photo_assistant.adapters.onnx_clip import OnnxClip
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.api.settings import MlSettings
from photo_assistant.app.ml_jobs import (
    AUTO_TAG,
    CLUSTER_FACES,
    DETECT_FACES,
    EMBED_CLIP,
    AutoTag,
    ClusterFaces,
    DetectFaces,
    EmbedClip,
    ImagePaths,
    MlJobPlanner,
)
from photo_assistant.app.people import People
from photo_assistant.app.search import SemanticSearch, SimilarPhotos
from photo_assistant.domain.tags import TagScore
from photo_assistant.ports import Repository
from photo_assistant.ports.ml import FaceAnalyzer, ModelStatus

Handler = Callable[[dict[str, object]], object]


@dataclass
class MlServices:
    settings: MlSettings
    store: SqliteMlStore
    clip: OnnxClip
    faces: FaceAnalyzer
    planner: MlJobPlanner
    search: SemanticSearch
    similar: SimilarPhotos
    people: People
    handlers: dict[str, Handler] = field(default_factory=dict)

    def status(self) -> dict[str, ModelStatus]:
        return {"clip": self.clip.status(), "faces": self.faces.status()}

    def backfill(self) -> int:
        return self.planner.backfill(self.store)

    def close(self) -> None:
        self.store.close()


def _face_analyzer(ml: MlSettings, data_root: Path) -> FaceAnalyzer:
    folder = ml.face_dir(data_root)
    if ml.face_model == "buffalo_l":
        return InsightFaceAnalyzer(
            folder, provider=ml.provider, det_size=ml.face_det_size, min_score=ml.face_score()
        )
    return YuNetSFaceAnalyzer(folder, min_score=ml.face_score(), det_max_edge=ml.face_det_size)


def build_ml_services(
    data_root: Path,
    ml: MlSettings,
    repo: Repository,
    library: ImagePaths,
    db: Database | None = None,
    on_tags: Callable[[int, Sequence[TagScore]], object] | None = None,
) -> MlServices:
    """``repo``/``library``: the app's Repository and LibraryStore; ``db``: the app's one
    Database (None: open the library database for this store alone, as tools do)."""
    store = SqliteMlStore(db) if db is not None else open_ml_store(data_root / "library.db")
    clip = OnnxClip(
        ml.clip_dir(data_root), ml.clip_model, provider=ml.provider, batch_size=ml.clip_batch_size
    )
    faces = _face_analyzer(ml, data_root)
    embed = EmbedClip(repo, library, store, clip)
    handlers: dict[str, Handler] = {
        EMBED_CLIP: embed,
        DETECT_FACES: DetectFaces(repo, library, store, faces),
        CLUSTER_FACES: ClusterFaces(store, faces.name, ml.cluster_params()),
        AUTO_TAG: AutoTag(embed, store, clip, ml.tag_params(), on_tags=on_tags),
    }
    tasks = {EMBED_CLIP: clip.name, DETECT_FACES: faces.name, AUTO_TAG: clip.name}
    model_of = {EMBED_CLIP: clip, AUTO_TAG: clip, DETECT_FACES: faces}
    planner = MlJobPlanner(
        repo, tasks if ml.enabled else {}, ready=lambda task: model_of[task].status().ready
    )
    return MlServices(
        settings=ml,
        store=store,
        clip=clip,
        faces=faces,
        planner=planner,
        search=SemanticSearch(clip, store, min_score=ml.search_min_score),
        similar=SimilarPhotos(store, clip.name),
        people=People(store),
        handlers=handlers,
    )
