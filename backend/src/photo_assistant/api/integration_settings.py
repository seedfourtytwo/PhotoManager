"""Settings for uploads, remote sources and the AI socket (same PA_ env prefix and .env).

Kept separate from ``Settings`` so this branch merges cleanly; the integrator may fold these
fields into ``Settings`` later (docs/wiring/ai-sources.md).
"""

from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from photo_assistant.adapters.ollama_ai import OllamaSettings
from photo_assistant.ports.sync import SyncOptions


class IntegrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

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
