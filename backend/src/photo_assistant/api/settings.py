from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration. The data root is the only machine-specific path (portability rule)."""

    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    data_root: Path = Path.home() / "PhotoAssistant" / "data"
    host: str = "127.0.0.1"
    port: int = 8420


@lru_cache
def get_settings() -> Settings:
    return Settings()
