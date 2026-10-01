from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from photo_assistant.api.integration_settings import IntegrationSettings
from photo_assistant.api.ml_settings import MlSettings
from photo_assistant.api.ops_settings import OpsSettings


class Settings(BaseSettings):
    """All configuration. The data root is the only machine-specific path (portability rule)."""

    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    data_root: Path = Path.home() / "PhotoAssistant" / "data"
    host: str = "127.0.0.1"  # set to a LAN/Tailscale address deliberately (login exists)
    port: int = 8420
    min_free_gb: float = 10.0
    thumb_edge: int = 640
    preview_edge: int = 2048
    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    vips_concurrency: int = 2  # the laptop does other work too (FEATURES 11.7)
    log_level: str = "INFO"
    # Host names the server answers to. Add the Tailscale name when remote access arrives (M6).
    allowed_hosts: list[str] = ["127.0.0.1", "localhost"]
    web_dir: Path | None = None  # built web app to serve at "/" (just run sets it)
    # argon2id cost (RFC 9106 low-memory profile). Tests lower it; never lower it in use.
    trash_purge_every_hours: float = 6.0  # how often the 30-day trash expiry runs
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    # Each area keeps its own settings class (same .env; field names in docs/wiring/*.md):
    # uploads, remote sources and AI (PA_*), local ML (PA_ML_*), backups (PA_*).
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    ml: MlSettings = Field(default_factory=MlSettings)
    ops: OpsSettings = Field(default_factory=OpsSettings)
    face_cluster_every_hours: float = 24.0  # global face clustering (deferred faces get people)

    @property
    def database_path(self) -> Path:
        return self.data_root / "library.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
