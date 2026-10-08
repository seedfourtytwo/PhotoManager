"""All configuration, read once (B22): one ``Settings`` with nested sections.

Every value comes from the environment or the ``.env`` file, under the names it always had:
``PA_<FIELD>`` for the top level, the integrations and ops sections, ``PA_ML_<FIELD>`` for the
ML section. The sections are plain models filled by ``Settings`` (they never read the
environment themselves), so one ``Settings()`` is the whole configuration of a process.

Every setting carries its meaning as the field's ``description``, one sentence for whoever
runs the app: ``scripts/settings_reference.py`` writes docs/guides/settings.md from them, and
a test fails when a setting has none or that file is stale.
"""

import logging
import os
from collections.abc import Mapping
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from photo_assistant.adapters.ollama_ai import OllamaSettings
from photo_assistant.domain.clustering import ClusterParams
from photo_assistant.domain.tags import TagParams
from photo_assistant.ports.sync import SyncOptions

log = logging.getLogger(__name__)

# --- sections --------------------------------------------------------------------------------


class IntegrationSettings(BaseModel):
    """Uploads, remote sources and the AI socket (``PA_*``)."""

    # uploads (phones, browsers)
    # a big RAW is ~80 MB; a HEIC ~3 MB
    upload_max_mb: float = Field(
        default=200.0,
        description=(
            "Largest single uploaded file, in MB; the upload is cut off as soon as it passes."
        ),
    )
    upload_max_files: int = Field(
        default=500,
        description="Most files in one upload request.",
    )

    # remote sources (rclone); credentials live in rclone's own config, never here
    rclone_binary: str = Field(
        default="rclone",
        description="The rclone program (name on the PATH, or a full path).",
    )
    rclone_config: Path | None = Field(
        default=None,
        description=(
            "rclone's config file, where the cloud sign-ins live; not set = rclone's own "
            "default, `~/.config/rclone/rclone.conf`."
        ),
    )
    rclone_tpslimit: float = Field(
        default=4.0,
        description=(
            "Most requests per second to a cloud source (MEGA blocks accounts that hammer"
            " it); `0` = no limit."
        ),
    )
    rclone_transfers: int = Field(
        default=2,
        description="Files rclone downloads at the same time.",
    )
    rclone_checkers: int = Field(
        default=4,
        description="Files rclone compares at the same time.",
    )
    rclone_timeout_hours: float = Field(
        default=6.0,
        description=(
            "A pull from a cloud source is stopped after this long; the next run continues."
        ),
    )
    # Proton Drive through Proton's own CLI; the sign-in lives in that tool, never here
    proton_drive_binary: str = Field(
        default="proton-drive",
        description="Proton's own `proton-drive` program (also looked for in `~/.local/bin`).",
    )

    # AI socket: off unless explicitly switched on
    ai_provider: Literal["none", "ollama"] = Field(
        default="none",
        description="`none`, or `ollama` to switch the optional AI features on.",
    )
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Where Ollama runs: the only address AI requests are sent to.",
    )
    ollama_caption_model: str | None = Field(
        default=None,
        description="Ollama model that describes photos; not set = no captions.",
    )
    ollama_plan_model: str | None = Field(
        default=None,
        description="Ollama model that proposes albums; not set = no album proposals.",
    )
    ollama_timeout_seconds: float = Field(
        default=120.0,
        description="How long to wait for one Ollama answer.",
    )

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


def _per_face_model(index: int) -> str:
    """The tuned default of every face model, for a setting's description."""
    return ", ".join(f"{tuned[index]} for {model}" for model, tuned in _FACE_DEFAULTS.items())


class MlSettings(BaseModel):
    """Local ML (``PA_ML_*``)."""

    enabled: bool = Field(
        default=True,
        description="`false`: no photo is queued for search, faces or tags.",
    )
    models_dir: Path | None = Field(
        default=None,
        description=(
            "Folder with the model files (`just models` fills it); not set = `<data root>/models`."
        ),
    )
    provider: Literal["auto", "cpu", "cuda"] = Field(
        default="auto",
        description=(
            "Where models run: `auto` (graphics card if this onnxruntime supports it, "
            "else processor), `cpu`, or `cuda` (an error if it is missing)."
        ),
    )
    # Immich Hugging Face repo name (immich-app/<name>). For French + English queries use
    # "XLM-Roberta-Large-Vit-B-32" (same 512-d image space as ViT-B-32__openai).
    clip_model: str = Field(
        default="ViT-B-32__openai",
        description=(
            "The search model, by its Immich name on Hugging Face. `XLM-Roberta-Large-"
            "Vit-B-32` understands French and English queries."
        ),
    )
    clip_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        description="Photos handed to the search model at once (1 to 256).",
    )
    face_model: FaceModel = Field(
        default="buffalo_l",
        description=(
            "Face model: `buffalo_l` (more accurate, non-commercial licence) or `yunet_sface`."
        ),
    )
    face_det_size: int = Field(
        default=640,
        ge=160,
        le=1920,
        description="Image size the face detector works at, in pixels (160 to 1920).",
    )
    face_min_score: float | None = Field(
        default=None,
        gt=0,
        lt=1,
        description=(
            "How sure the detector must be that something is a face (0 to 1); not set = "
            f"{_per_face_model(0)}."
        ),
    )
    face_max_distance: float | None = Field(
        default=None,
        gt=0,
        le=2,
        description=(
            "How different two faces may be and still count as one person; not set = "
            f"{_per_face_model(1)}."
        ),
    )
    face_min_faces: int = Field(
        default=3,
        ge=1,
        description="Faces needed before a new person is suggested.",
    )
    tag_margin: float = Field(
        default=0.03,
        description=(
            "How clearly a tag must beat the neutral baseline: higher = fewer, surer tags."
        ),
    )
    tag_max_tags: int = Field(
        default=3,
        ge=1,
        description="Most automatic tags per photo.",
    )
    search_min_score: float | None = Field(
        default=None,
        description="Search hits scoring below this are dropped; not set = keep all.",
    )

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

    backup_enabled: bool = Field(
        default=True,
        description=(
            "`false` stops scheduled backups from running inside the server (`just backup"
            " run` still works)."
        ),
    )
    backup_poll_seconds: float = Field(
        default=60.0,
        description="How often the server checks whether a backup is due.",
    )
    # FEATURES 9b.8
    backup_restore_sample: int = Field(
        default=20,
        description="Photos restored and compared in one restore test.",
    )
    backup_scratch_dir: Path | None = Field(
        default=None,
        description=(
            "Where a restore test unpacks its sample; not set = the system temp folder. "
            "Must be outside the library."
        ),
    )
    # keys the app makes for its backups; None = ~/.config/photo-assistant/backup-keys.
    # Always outside the library: a backup must not carry its own key.
    backup_key_dir: Path | None = Field(
        default=None,
        description=(
            "Where the app keeps the backup encryption keys it makes; not set = "
            "`~/.config/photo-assistant/backup-keys`. Must be outside the library."
        ),
    )
    restic_binary: str = Field(
        default="restic",
        description="The restic program (name on the PATH, or a full path).",
    )
    restic_cache_dir: Path | None = Field(
        default=None,
        description="restic's cache folder; not set = restic's own default, `~/.cache/restic`.",
    )


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

    data_root: Path = Field(
        default=Path.home() / "PhotoAssistant" / "data",
        description=(
            "The library folder: database, originals, thumbnails, logs. The only machine-"
            "specific path."
        ),
    )
    # set to a LAN/Tailscale address deliberately (login exists)
    host: str = Field(
        default="127.0.0.1",
        description=(
            "Address the server listens on. Keep it on 127.0.0.1 and let Tailscale "
            "forward to it (remote-access.md)."
        ),
    )
    port: int = Field(
        default=8420,
        description="Port the server listens on.",
    )
    min_free_gb: float = Field(
        default=10.0,
        description=(
            "An import pauses instead of leaving less than this free on the library disk;"
            " `just doctor` warns near it."
        ),
    )
    thumb_edge: int = Field(
        default=640,
        description="Longest edge of a thumbnail, in pixels.",
    )
    preview_edge: int = Field(
        default=2048,
        description="Longest edge of a preview (the big view), in pixels.",
    )
    worker_enabled: bool = Field(
        default=True,
        description=(
            "`false` starts the server without its background work: no job worker "
            "(previews, imports, ML, backups) and no periodic tasks."
        ),
    )
    worker_poll_seconds: float = Field(
        default=1.0,
        description="How often an idle job worker looks for a new job.",
    )
    # the laptop does other work too (FEATURES 11.7)
    vips_concurrency: int = Field(
        default=2,
        description="Threads libvips may use to render one image.",
    )
    # 0 = max(1, cores - 2) (C28)
    preview_workers: int = Field(
        default=0,
        description=(
            "Previews rendered at the same time; `0` means two fewer than the processor's"
            " cores, at least 1."
        ),
    )
    log_level: str = Field(
        default="INFO",
        description="How much is logged: `DEBUG`, `INFO`, `WARNING` or `ERROR`.",
    )
    # Host names the server answers to. Add the Tailscale name when remote access arrives (M6).
    # NoDecode: read by _host_names below, which takes more spellings than strict JSON.
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default=["127.0.0.1", "localhost"],
        description=(
            "Host names the server answers to; any other name is refused. Add the "
            "Tailscale name here (remote-access.md)."
        ),
    )
    # Who may tell the server "this request arrived over https, from that address"
    # (X-Forwarded-Proto / X-Forwarded-For): the TLS proxy in front, as uvicorn sees it.
    # Comma-separated addresses or networks. Docker + tailscale serve: the Docker gateway.
    trusted_proxies: str = Field(
        default="127.0.0.1",
        description=(
            "Addresses or networks of the https proxy in front of the server, comma-"
            "separated. Only these may say a request arrived over https and from which "
            "device. In Docker: the Docker networks (server.env.example)."
        ),
    )
    web_dir: Path | None = Field(
        default=None,
        description=(
            "Folder with the built web app, served at `/`. `just run`, the systemd unit "
            "and the Docker image set it; not set = API only."
        ),
    )
    # argon2id cost (RFC 9106 low-memory profile). Tests lower it; never lower it in use.
    trash_purge_every_hours: float = Field(
        default=6.0,
        description=(
            "How often the server deletes photos that have been in the trash for 30 days."
        ),
    )
    argon2_time_cost: int = Field(
        default=3,
        description="Work factor of the PIN hash. Tests lower it; never lower it in use.",
    )
    argon2_memory_kib: int = Field(
        default=65536,
        description="Memory used by one PIN hash, in KiB. Tests lower it; never lower it in use.",
    )
    # Sections, filled from their flat names (see _FlatSections and docs/guides/settings.md):
    # uploads, remote sources and AI (PA_*), local ML (PA_ML_*), backups (PA_*).
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    ml: MlSettings = Field(default_factory=MlSettings)
    ops: OpsSettings = Field(default_factory=OpsSettings)
    face_cluster_every_hours: float = Field(
        default=24.0,
        description="How often faces are regrouped into people.",
    )
    # E2E only: adds POST /__test/reset. Refused unless the server stays on this machine.
    test_mode: bool = Field(
        default=False,
        description=(
            "End-to-end tests only: adds `POST /__test/reset`, which wipes the library. "
            "Refused unless host and allowed hosts are loopback. Never set it on a real "
            "library."
        ),
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _host_names(cls, value: object) -> object:
        """``["a","b"]`` (JSON), ``[a,b]`` (what systemd's EnvironmentFile leaves of that: it
        strips the double quotes) or ``a,b``."""
        if not isinstance(value, str):
            return value
        names = (name.strip().strip("\"'") for name in value.strip().strip("[]").split(","))
        return [name for name in names if name]

    def preview_threads(self) -> int:
        """Preview renders in parallel: leave two cores to the import and the web server."""
        return self.preview_workers or max(1, (os.cpu_count() or 1) - 2)


def unknown_setting_names(environ: Mapping[str, str]) -> list[str]:
    """The ``PA_*`` names in ``environ`` that are no setting: almost always a misspelt one
    (``PA_ALLOWED_HOST``), which would otherwise be ignored without a word."""
    known = {f"PA_{field}".upper() for field in Settings.model_fields}
    for model, prefix in _SECTIONS.values():
        known |= {f"{prefix}{field}".upper() for field in model.model_fields}
    return sorted(n for n in environ if n.upper().startswith("PA_") and n.upper() not in known)


def warn_about_unknown_settings() -> None:
    for name in unknown_setting_names(os.environ):
        log.warning("%s is set but is not a setting of this app: check its spelling", name)


@lru_cache
def get_settings() -> Settings:
    return Settings()
