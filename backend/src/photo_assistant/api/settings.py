from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration. The data root is the only machine-specific path (portability rule)."""

    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    data_root: Path = Path.home() / "PhotoAssistant" / "data"
    host: str = "127.0.0.1"  # M1 has no login yet: never listen beyond this machine
    port: int = 8420
    min_free_gb: float = 10.0
    thumb_edge: int = 640
    preview_edge: int = 2048
    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    vips_concurrency: int = 2  # the laptop does other work too (FEATURES 11.7)
    log_level: str = "INFO"
    web_dir: Path | None = None  # built web app to serve at "/" (just run sets it)

    @property
    def database_path(self) -> Path:
        return self.data_root / "library.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
