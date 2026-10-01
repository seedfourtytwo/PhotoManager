"""Settings for local ML (environment ``PA_ML_*`` or ``.env``), kept apart from ``Settings``
until the integrator folds them in (docs/wiring/ml.md)."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from photo_assistant.domain.clustering import ClusterParams
from photo_assistant.domain.tags import TagParams

FaceModel = Literal["buffalo_l", "yunet_sface"]

# Tuned per model: ArcFace (buffalo_l) as Immich; SFace embeddings sit further apart.
_FACE_DEFAULTS: dict[str, tuple[float, float]] = {  # (min detection score, cluster distance)
    "buffalo_l": (0.7, 0.5),
    "yunet_sface": (0.8, 0.6),
}


class MlSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_ML_", env_file=".env", extra="ignore")

    enabled: bool = True
    models_dir: Path | None = None  # default: <data_root>/models
    provider: Literal["auto", "cpu", "cuda"] = "auto"
    # Immich Hugging Face repo name (immich-app/<name>). For French + English queries use
    # "XLM-Roberta-Large-Vit-B-32" (same 512-d image space as ViT-B-32__openai).
    clip_model: str = "ViT-B-32__openai"
    clip_batch_size: int = Field(default=16, ge=1, le=256)
    face_model: FaceModel = "buffalo_l"
    face_det_size: int = Field(default=640, ge=160, le=1920)
    face_min_score: float | None = Field(default=None, gt=0, lt=1)
    face_max_distance: float | None = Field(default=None, gt=0, le=2)
    face_min_faces: int = Field(default=3, ge=1)
    tag_margin: float = 0.03
    tag_max_tags: int = Field(default=3, ge=1)
    search_min_score: float | None = None

    def models_root(self, data_root: Path) -> Path:
        return (self.models_dir or data_root / "models").expanduser()

    def clip_dir(self, data_root: Path) -> Path:
        return self.models_root(data_root) / "clip" / self.clip_model

    def face_dir(self, data_root: Path) -> Path:
        if self.face_model == "buffalo_l":
            return self.models_root(data_root) / "insightface" / "buffalo_l"
        return self.models_root(data_root) / "opencv"

    def face_score(self) -> float:
        return self.face_min_score or _FACE_DEFAULTS[self.face_model][0]

    def cluster_params(self) -> ClusterParams:
        distance = self.face_max_distance or _FACE_DEFAULTS[self.face_model][1]
        return ClusterParams(max_distance=distance, min_faces=self.face_min_faces)

    def tag_params(self) -> TagParams:
        return TagParams(margin=self.tag_margin, max_tags=self.tag_max_tags)
