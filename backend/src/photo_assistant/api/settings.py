"""All configuration, read once (B22): one ``Settings`` with nested sections.

Every value comes from the environment or the ``.env`` file, under the names it always had:
``PA_<FIELD>`` for the top level, the integrations and ops sections, ``PA_ML_<FIELD>`` for the
ML section. The sections are plain models filled by ``Settings`` (they never read the
environment themselves), so one ``Settings()`` is the whole configuration of a process.
"""

import os
from collections.abc import Mapping
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from photo_assistant.adapters.ollama_ai import OllamaSettings
from photo_assistant.domain.clustering import ClusterParams
from photo_assistant.domain.tags import TagParams
from photo_assistant.ports.sync import SyncOptions

# --- sections --------------------------------------------------------------------------------


class IntegrationSettings(BaseModel):
    """Uploads, remote sources and the AI socket (``PA_*``)."""

    # uploads (phones, browsers)
    upload_max_mb: float = 200.0  # a big RAW is ~80 MB; a HEIC ~3 MB
    upload_max_files: int = 500  # per request

    # remote sources (rclone); credentials live in rclone's own config, never here
    rclone_binary: str = "rclone"
    rclone_config: Path | None = None  # None: rclone's default (~/.config/rclone/rclone.conf)
    rclone_tpslimit: float = 4.0  # MEGA blocks accounts that hammer it
    rclone_transfers: int = 2
    rclone_checkers: int = 4
    rclone_timeout_hours: float = 6.0
    # Proton Drive through Proton's own CLI; the sign-in lives in that tool, never here
    proton_drive_binary: str = "proton-drive"

    # AI socket: off unless explicitly switched on
    ai_provider: Literal["none", "ollama"] = "none"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_caption_model: str | None = None
    ollama_plan_model: str | None = None
    ollama_timeout_seconds: float = 120.0

    @property
    def upload_max_bytes(self) -> int:
        return int(self.upload_max_mb * 1000**2)

    def sync_options(self) -> SyncOptions:
        return SyncOptions(
            tpslimit=self.rclone_tpslimit,
            transfers=self.rclone_transfers,
            checkers=self.rclone_checkers,
            timeout_seconds=timedelta(hours=self.rclone_timeout_hours).total_seconds(),
        )

    def ollama(self) -> OllamaSettings | None:
        if self.ai_provider != "ollama":
            return None
        return OllamaSettings(
            base_url=self.ollama_base_url,
            caption_model=self.ollama_caption_model,
            plan_model=self.ollama_plan_model,
            timeout_seconds=self.ollama_timeout_seconds,
        )


FaceModel = Literal["buffalo_l", "yunet_sface"]

# Tuned per model: ArcFace (buffalo_l) as Immich; SFace embeddings sit further apart.
_FACE_DEFAULTS: dict[str, tuple[float, float]] = {  # (min detection score, cluster distance)
    "buffalo_l": (0.7, 0.5),
    "yunet_sface": (0.8, 0.6),
}


class MlSettings(BaseModel):
    """Local ML (``PA_ML_*``)."""

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


class OpsSettings(BaseModel):
    """Backups and operations (``PA_*``)."""

    backup_enabled: bool = True  # scheduled backups run inside the server process
    backup_poll_seconds: float = 60.0  # how often the server looks for due backups
    backup_restore_sample: int = 20  # photos per restore test (FEATURES 9b.8)
    backup_scratch_dir: Path | None = None  # restore tests unpack here; None = system temp
    # keys the app makes for its backups; None = ~/.config/photo-assistant/backup-keys.
    # Always outside the library: a backup must not carry its own key.
    backup_key_dir: Path | None = None
    restic_binary: str = "restic"
    restic_cache_dir: Path | None = None  # None = restic's default (~/.cache/restic)


# --- the one Settings ------------------------------------------------------------------------

_SECTIONS: dict[str, tuple[type[BaseModel], str]] = {
    "integrations": (IntegrationSettings, "PA_"),
    "ml": (MlSettings, "PA_ML_"),
    "ops": (OpsSettings, "PA_"),
}


class _FlatSections(PydanticBaseSettingsSource):
    """Fills each section from its flat names (``PA_UPLOAD_MAX_MB`` -> integrations,
    ``PA_ML_CLIP_MODEL`` -> ml): the environment first, then the ``.env`` file."""

    def __init__(self, settings_cls: type[BaseSettings], dotenv: Mapping[str, str | None]) -> None:
        super().__init__(settings_cls)
        self._dotenv = dotenv  # what pydantic-settings read from the .env file

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False  # unused: __call__ reads whole sections

    def _raw(self) -> dict[str, str]:
        values = {k.upper(): v for k, v in self._dotenv.items() if v is not None}
        return values | {k.upper(): v for k, v in os.environ.items()}

    def __call__(self) -> dict[str, Any]:
        raw = self._raw()
        sections: dict[str, Any] = {}
        for name, (model, prefix) in _SECTIONS.items():
            found = {
                field: raw[key]
                for field in model.model_fields
                if (key := f"{prefix}{field}".upper()) in raw
            }
            if found:
                sections[name] = found
        return sections


class Settings(BaseSettings):
    """All configuration. The data root is the only machine-specific path (portability rule)."""

    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        dotenv = (
            dotenv_settings.env_vars if isinstance(dotenv_settings, DotEnvSettingsSource) else {}
        )
        sections = _FlatSections(settings_cls, dotenv)
        return init_settings, env_settings, dotenv_settings, sections, file_secret_settings

    data_root: Path = Path.home() / "PhotoAssistant" / "data"
    host: str = "127.0.0.1"  # set to a LAN/Tailscale address deliberately (login exists)
    port: int = 8420
    min_free_gb: float = 10.0
    thumb_edge: int = 640
    preview_edge: int = 2048
    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    vips_concurrency: int = 2  # the laptop does other work too (FEATURES 11.7)
    preview_workers: int = 0  # threads rendering previews; 0 = max(1, cores - 2) (C28)
    log_level: str = "INFO"
    # Host names the server answers to. Add the Tailscale name when remote access arrives (M6).
    allowed_hosts: list[str] = ["127.0.0.1", "localhost"]
    # Who may tell the server "this request arrived over https, from that address"
    # (X-Forwarded-Proto / X-Forwarded-For): the TLS proxy in front, as uvicorn sees it.
    # Comma-separated addresses or networks. Docker + tailscale serve: the Docker gateway.
    trusted_proxies: str = "127.0.0.1"
    web_dir: Path | None = None  # built web app to serve at "/" (just run sets it)
    # argon2id cost (RFC 9106 low-memory profile). Tests lower it; never lower it in use.
    trash_purge_every_hours: float = 6.0  # how often the 30-day trash expiry runs
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    # Sections, filled from their flat names (see _FlatSections and docs/wiring/*.md):
    # uploads, remote sources and AI (PA_*), local ML (PA_ML_*), backups (PA_*).
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    ml: MlSettings = Field(default_factory=MlSettings)
    ops: OpsSettings = Field(default_factory=OpsSettings)
    face_cluster_every_hours: float = 24.0
    # E2E only: adds POST /__test/reset. Refused unless the server stays on this machine.
    test_mode: bool = False

    def preview_threads(self) -> int:
        """Preview renders in parallel: leave two cores to the import and the web server."""
        return self.preview_workers or max(1, (os.cpu_count() or 1) - 2)


@lru_cache
def get_settings() -> Settings:
    return Settings()
