"""Request and response shapes (the public contract the web client is generated from)."""

from datetime import datetime

from pydantic import BaseModel, Field

from photo_assistant.domain.model import Asset, Source


class SourceIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    path: str


class SourcePatch(BaseModel):
    enabled: bool | None = None
    label: str | None = Field(default=None, min_length=1, max_length=100)


class SourceOut(BaseModel):
    id: int
    label: str
    path: str
    enabled: bool
    kind: str

    @classmethod
    def of(cls, s: Source) -> "SourceOut":
        return cls(id=s.id, label=s.label, path=s.root, enabled=s.enabled, kind=s.kind)


class ImageRef(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None


class AssetOut(BaseModel):
    id: int
    taken_at: datetime
    tz_offset_minutes: int | None
    date_source: str
    width: int | None
    height: int | None
    kind: str
    thumb: ImageRef | None
    preview_ready: bool

    @classmethod
    def of(cls, a: Asset) -> "AssetOut":
        thumb = ImageRef(url=f"/api/assets/{a.id}/thumb") if a.thumb_path else None
        return cls(
            id=a.id,
            taken_at=a.taken_at,
            tz_offset_minutes=a.tz_offset_minutes,
            date_source=a.date_source.value,
            width=a.width,
            height=a.height,
            kind=a.kind.value,
            thumb=thumb,
            preview_ready=a.preview_path is not None,
        )


class Origin(BaseModel):
    source_id: int
    source_label: str
    relative_path: str


class AssetDetail(AssetOut):
    byte_size: int
    mime_type: str | None
    camera_make: str | None
    camera_model: str | None
    latitude: float | None
    longitude: float | None
    variant_of: int | None
    imported_at: datetime
    origins: list[Origin]


class AssetPage(BaseModel):
    items: list[AssetOut]
    next_cursor: str | None


class Queued(BaseModel):
    job_id: int
    source_id: int
