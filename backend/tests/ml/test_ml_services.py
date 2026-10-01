"""The ML composition helper, end to end with the real Worker, SQLite and synthetic models."""

from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.api.ml_services import build_ml_services
from photo_assistant.api.ml_settings import MlSettings
from photo_assistant.app.ml_jobs import AUTO_TAG, DETECT_FACES, EMBED_CLIP, TaskStatus
from photo_assistant.app.worker import Worker
from tests.factories import NOW, new_asset
from tests.ml.test_face_adapters import buffalo, red_image
from tests.ml.test_onnx_clip import make_clip_folder, save_png


class Clock:
    def now(self) -> datetime:
        return NOW


def test_settings_defaults_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    default = MlSettings(_env_file=None)  # type: ignore[call-arg]
    root = Path("/data")
    assert default.clip_dir(root) == Path("/data/models/clip/ViT-B-32__openai")
    assert default.face_dir(root) == Path("/data/models/insightface/buffalo_l")
    assert default.cluster_params().max_distance == 0.5 and default.face_score() == 0.7
    monkeypatch.setenv("PA_ML_FACE_MODEL", "yunet_sface")
    monkeypatch.setenv("PA_ML_MODELS_DIR", "/models")
    monkeypatch.setenv("PA_ML_FACE_MIN_FACES", "5")
    custom = MlSettings(_env_file=None)  # type: ignore[call-arg]
    assert custom.face_dir(root) == Path("/models/opencv")
    assert custom.cluster_params().max_distance == 0.6
    assert custom.cluster_params().min_faces == 5
    assert custom.face_score() == 0.8
    assert custom.tag_params().max_tags == 3


def setup(root: Path, ml: MlSettings) -> tuple:
    repo = SqliteRepository(open_database(root / "library.db"))
    library = DiskLibraryStore(root)
    services = build_ml_services(root, ml, repo, library)
    asset = repo.add_asset(new_asset(1), NOW)
    target = root / new_asset(1).library_path
    target.parent.mkdir(parents=True)
    save_png(target, red_image())
    return repo, services, asset


def test_without_models_jobs_record_model_missing(tmp_path: Path) -> None:
    repo, services, asset = setup(tmp_path, MlSettings(_env_file=None))  # type: ignore[call-arg]
    services.planner.for_asset(asset)
    Worker(repo, services.handlers, Clock()).run_until_idle()
    for task, model in [(EMBED_CLIP, "ViT-B-32__openai"), (DETECT_FACES, "buffalo_l"),
                        (AUTO_TAG, "ViT-B-32__openai")]:  # fmt: skip
        assert services.store.task_status(asset, task, model) == TaskStatus.MODEL_MISSING
    assert not repo.list_jobs("failed")
    assert not any(s.ready for s in services.status().values())
    assert services.backfill() == 3  # all three are re-queued (+ one global clustering)
    services.close()


def test_with_models_photos_are_embedded_tagged_and_people_found(tmp_path: Path) -> None:
    models = tmp_path / "models"
    make_clip_folder(models / "clip" / "tiny")
    buffalo(models / "insightface" / "buffalo_l")
    ml = MlSettings(_env_file=None, clip_model="tiny", face_min_faces=1, provider="cpu")  # type: ignore[call-arg]
    repo, services, asset = setup(tmp_path, ml)
    services.planner.after(lambda payload: None)({"asset_id": asset})
    Worker(repo, services.handlers, Clock()).run_until_idle()

    assert not repo.list_jobs("failed")
    assert services.store.clip_vector(asset, "tiny") is not None
    assert services.store.task_status(asset, AUTO_TAG, "tiny") == TaskStatus.DONE
    (person,) = services.people.list_all({asset})
    assert person.face_count == 1
    assert services.people.assets(person.id, {asset}) == [asset]
    hits = services.search("a", {asset}, 5)
    assert [h.asset_id for h in hits] == [asset]
    assert services.similar(asset, {asset}, 5) == []
    assert all(s.ready for s in services.status().values())
    services.close()


def test_yunet_can_be_chosen(tmp_path: Path) -> None:
    ml = MlSettings(_env_file=None, face_model="yunet_sface")  # type: ignore[call-arg]
    _, services, _ = setup(tmp_path, ml)
    assert services.faces.name == "yunet_sface"
    services.close()


def test_disabled_ml_plans_nothing(tmp_path: Path) -> None:
    repo, services, asset = setup(tmp_path, MlSettings(_env_file=None, enabled=False))  # type: ignore[call-arg]
    services.planner.for_asset(asset)
    assert repo.list_jobs("queued") == []
    services.close()
