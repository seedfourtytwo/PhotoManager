"""Small builders so tests say only what matters to them."""

from datetime import UTC, datetime

from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.media_types import MediaKind
from photo_assistant.domain.model import NewAsset

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def new_asset(n: int = 1, taken_at: datetime | None = None, **overrides: object) -> NewAsset:
    values: dict[str, object] = {
        "content_hash": f"{n:064x}",
        "kind": MediaKind.PHOTO,
        "mime_type": "image/jpeg",
        "byte_size": 1000 + n,
        "width": 4000,
        "height": 3000,
        "taken_at": taken_at or datetime(2020, 1, 1, 12, 0),
        "tz_offset_minutes": None,
        "date_source": DateSource.EXIF,
        "latitude": None,
        "longitude": None,
        "camera_make": "Apple",
        "camera_model": "iPhone",
        "orientation": 1,
        "library_path": f"originals/2020/01/{n:064x}.jpg",
    }
    values.update(overrides)
    return NewAsset(**values)  # type: ignore[arg-type]
