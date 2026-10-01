"""Settings for backups and operations (PA_ prefix, same .env as Settings).

Kept apart from ``api/settings.py`` so the ops branch merges without conflicts; the integrator
may fold these fields into ``Settings`` (docs/wiring/ops.md).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class OpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    backup_enabled: bool = True  # scheduled backups run inside the server process
    backup_poll_seconds: float = 60.0  # how often the server looks for due backups
    backup_restore_sample: int = 20  # photos per restore test (FEATURES 9b.8)
    backup_scratch_dir: Path | None = None  # restore tests unpack here; None = system temp
    restic_binary: str = "restic"
    restic_cache_dir: Path | None = None  # None = restic's default (~/.cache/restic)
