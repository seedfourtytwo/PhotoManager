"""Readable logs: plain lines on the console, JSON lines in data/logs (rotated)."""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_STANDARD = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(data_root: Path, level: str = "INFO") -> None:
    log_dir = data_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "photo-assistant.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("photo_assistant")
    root.handlers[:] = [file_handler, console]
    root.setLevel(level)
    root.propagate = False


def shutdown_logging() -> None:
    root = logging.getLogger("photo_assistant")
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
