"""Background jobs for local ML (FEATURES 2.7-2.10): one job per asset and task, idempotent.

Each handler records a status per (asset, task, model) so re-runs skip finished work and a
missing model shows up as "model_missing" (fixed by `just models` + a backfill) instead of a
job that fails forever. Jobs read the best rendition the library has: preview, else
thumbnail, else the original — all orientation-corrected by the image loader.
"""

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from photo_assistant.domain.clustering import Action, ClusterParams, decide
from photo_assistant.domain.tags import (
    VOCABULARY,
    TagModel,
    TagParams,
    TagSpec,
    build_tag_model,
    is_screen_or_document,
    zero_shot_tags,
)
from photo_assistant.ports import Repository
from photo_assistant.ports.ml import (
    FaceAnalyzer,
    ImageEmbedder,
    MlStore,
    ModelUnavailableError,
    TextEmbedder,
)

EMBED_CLIP = "embed_clip"
DETECT_FACES = "detect_faces"
CLUSTER_FACES = "cluster_faces"
AUTO_TAG = "auto_tag"
PER_ASSET_TASKS = (EMBED_CLIP, DETECT_FACES, AUTO_TAG)

Handler = Callable[[dict[str, object]], object]


class TaskStatus(StrEnum):
    DONE = "done"
    MODEL_MISSING = "model_missing"  # re-queued by the backfill once models are downloaded
    UNREADABLE = "unreadable"  # the image could not be decoded


class ImagePaths(Protocol):
    def absolute(self, relative_path: str) -> Path: ...


def asset_id_of(payload: Mapping[str, object]) -> int:
    value = payload.get("asset_id")
    if value is None:
        raise ValueError("job payload needs an asset_id")
    return int(str(value))


def best_image(repo: Repository, library: ImagePaths, asset_id: int) -> Path | None:
    asset = repo.get_asset(asset_id)
    if asset is None:
        return None  # removed since the job was queued: nothing to do
    relative = asset.preview_path or asset.thumb_path or asset.library_path
    return library.absolute(relative)


class _AssetTask:
    """Shared skeleton: skip when done, turn known failures into statuses."""

    task: str

    def __init__(self, repo: Repository, library: ImagePaths, store: MlStore, model: str) -> None:
        self._repo, self._library, self._store, self._model = repo, library, store, model

    def __call__(self, payload: dict[str, object]) -> None:
        self.run(asset_id_of(payload))

    def run(self, asset_id: int) -> TaskStatus | None:
        current = self._store.task_status(asset_id, self.task, self._model)
        if current == TaskStatus.DONE:
            return TaskStatus.DONE
        path = best_image(self._repo, self._library, asset_id)
        if path is None:
            return None
        try:
            self._work(asset_id, path)
        except ModelUnavailableError as exc:
            return self._record(asset_id, TaskStatus.MODEL_MISSING, str(exc))
        except ValueError as exc:  # the loader's "cannot decode"
            return self._record(asset_id, TaskStatus.UNREADABLE, str(exc))
        return self._record(asset_id, TaskStatus.DONE, None)

    def _record(self, asset_id: int, status: TaskStatus, detail: str | None) -> TaskStatus:
        self._store.set_task_status(asset_id, self.task, self._model, status, detail)
        return status

    def _work(self, asset_id: int, path: Path) -> None:
        raise NotImplementedError


class EmbedClip(_AssetTask):
    task = EMBED_CLIP

    def __init__(
        self, repo: Repository, library: ImagePaths, store: MlStore, embedder: ImageEmbedder
    ) -> None:
        super().__init__(repo, library, store, embedder.name)
        self._embedder = embedder

    @property
    def model(self) -> str:
        return self._model

    def _work(self, asset_id: int, path: Path) -> None:
        (vector,) = self._embedder.embed_images([path])
        self._store.save_clip(asset_id, self._model, vector)


class DetectFaces(_AssetTask):
    task = DETECT_FACES

    def __init__(
        self, repo: Repository, library: ImagePaths, store: MlStore, analyzer: FaceAnalyzer
    ) -> None:
        super().__init__(repo, library, store, analyzer.name)
        self._analyzer = analyzer

    def _work(self, asset_id: int, path: Path) -> None:
        faces = self._analyzer.detect(path)
        if self._store.replace_faces(asset_id, self._model, faces):
            self._repo.enqueue(CLUSTER_FACES, {"asset_id": asset_id})


class ClusterFaces:
    """``{"asset_id": n}``: first pass for that photo's new faces (queued by detect_faces).
    ``{}``: every new face, then every deferred or unmatched face again (backfill, nightly)."""

    def __init__(self, store: MlStore, model: str, params: ClusterParams) -> None:
        self._store, self._model, self._params = store, model, params

    def __call__(self, payload: dict[str, object]) -> None:
        asset_id = asset_id_of(payload) if "asset_id" in payload else None
        for face_id in self._store.faces_to_cluster(self._model, deferred=False, asset_id=asset_id):
            self._step(face_id, deferred=False)
        if asset_id is None:
            for face_id in self._store.faces_to_cluster(self._model, deferred=True):
                self._step(face_id, deferred=True)

    def _step(self, face_id: int, *, deferred: bool) -> None:
        reach, needed = self._params.max_distance, self._params.min_faces
        matches = self._store.count_face_matches(face_id, reach, limit=needed)
        person = self._store.nearest_person(face_id, reach)
        decision = decide(matches, person, self._params, deferred=deferred)
        if decision.action is Action.ASSIGN and decision.person_id is not None:
            self._store.assign_face(face_id, decision.person_id)
        elif decision.action is Action.NEW_PERSON:
            self._store.create_person(face_id)
        elif not deferred:
            # Deferred or unmatched: stays in the queue of the next global pass, so a face
            # whose look-alikes arrive later still finds its person.
            self._store.mark_deferred(face_id)


class AutoTag:
    task = AUTO_TAG

    def __init__(
        self,
        embed: EmbedClip,
        store: MlStore,
        text: TextEmbedder,
        params: TagParams,
        vocabulary: Sequence[TagSpec] = VOCABULARY,
    ) -> None:
        self._embed, self._store, self._text = embed, store, text
        self._params, self._vocabulary = params, vocabulary
        self._tag_model: TagModel | None = None

    def __call__(self, payload: dict[str, object]) -> None:
        asset_id = asset_id_of(payload)
        model = self._embed.model
        if self._store.task_status(asset_id, AUTO_TAG, model) == TaskStatus.DONE:
            return
        embedded = self._embed.run(asset_id)
        if embedded is None:
            return
        if embedded is not TaskStatus.DONE:
            self._store.set_task_status(asset_id, AUTO_TAG, model, embedded, "no CLIP vector")
            return
        try:
            tag_model = self._prototypes()
        except ModelUnavailableError as exc:
            self._store.set_task_status(
                asset_id, AUTO_TAG, model, TaskStatus.MODEL_MISSING, str(exc)
            )
            return
        self._tag(asset_id, model, tag_model)

    def _prototypes(self) -> TagModel:
        if self._tag_model is None:  # ~60 prompts, embedded once per process
            self._tag_model = build_tag_model(self._text.embed_text, self._vocabulary)
        return self._tag_model

    def _tag(self, asset_id: int, model: str, tag_model: TagModel) -> None:
        vector = self._store.clip_vector(asset_id, model)
        if vector is None:  # pragma: no cover - EmbedClip just stored it
            raise LookupError(f"no CLIP vector for asset {asset_id}")
        tags = zero_shot_tags(vector, tag_model, self._params)
        flag = is_screen_or_document(tags, self._vocabulary)
        self._store.replace_model_tags(asset_id, model, tags, flag)
        self._store.set_task_status(asset_id, AUTO_TAG, model, TaskStatus.DONE)


class MlJobPlanner:
    """Queues ML work. ``models`` maps each enabled per-asset task to its model name."""

    def __init__(
        self,
        repo: Repository,
        models: Mapping[str, str],
        ready: Callable[[str], bool] = lambda task: True,
    ) -> None:
        """``ready(task)``: is that task's model installed? (C31: no jobs that can only fail;
        ``just ml-backfill`` queues the work once the files are there.)"""
        self._repo = repo
        self._models = {task: models[task] for task in PER_ASSET_TASKS if task in models}
        self._ready = ready

    def for_asset(self, asset_id: int) -> None:
        for task in self._models:
            if self._ready(task):
                self._repo.enqueue(task, {"asset_id": asset_id})

    def after(self, handler: Handler) -> Handler:
        """Wrap the preview handler so ML runs once the large rendition exists."""

        def run_then_plan(payload: dict[str, object]) -> object:
            result = handler(payload)
            self.for_asset(asset_id_of(payload))
            return result

        return run_then_plan

    def backfill(self, store: MlStore, page_size: int = 500) -> int:
        """Queue every unfinished (asset, task) — after `just models` or a model change.
        Work that is already waiting is not queued again; returns how much was added."""
        # read once: asking the queue per job (enqueue_once) scans every waiting job each time
        waiting = {
            (job["kind"], job["payload"].get("asset_id"))
            for job in self._repo.list_jobs("queued")
            if isinstance(job["payload"], dict)
        }
        count, cursor = 0, None
        while True:
            page = self._repo.list_assets(page_size, cursor)
            for asset in page.items:
                count += self._queue_unfinished(store, asset.id, waiting)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        if DETECT_FACES in self._models and self._ready(DETECT_FACES):
            self._repo.enqueue_once(CLUSTER_FACES)
        return count

    def _queue_unfinished(
        self, store: MlStore, asset_id: int, waiting: set[tuple[object, object]]
    ) -> int:
        queued = 0
        for task, model in self._models.items():
            if not self._ready(task) or (task, asset_id) in waiting:
                continue
            if store.task_status(asset_id, task, model) != TaskStatus.DONE:
                self._repo.enqueue(task, {"asset_id": asset_id})
                queued += 1
        return queued
