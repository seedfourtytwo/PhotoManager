"""Request and response shapes (the public contract the web client is generated from)."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from photo_assistant.domain.access import Role, User
from photo_assistant.domain.edit_recipe import Recipe
from photo_assistant.domain.export_naming import MAX_EDGE, ExportOptions, Folders, Naming
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.model import MAX_ID, Source
from photo_assistant.ports.library import AlbumInfo, AssetView

# Contract: capture times are local wall-clock to the second (`2019-07-04T18:30:00`); a date
# guessed from a file's mtime carries microseconds that the contract (and the web) don't take.
WallClock = Annotated[
    datetime, PlainSerializer(lambda d: d.isoformat(timespec="seconds"), return_type=str)
]
Id = Annotated[int, Field(ge=1, le=MAX_ID)]  # a SQLite rowid (QA A11)

# --- accounts --------------------------------------------------------------------------------


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    disabled: bool

    @classmethod
    def of(cls, u: User) -> "UserOut":
        return cls(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            role=u.role,
            disabled=u.disabled,
        )


class AccountName(BaseModel):
    """What the login screen shows before anyone is signed in: names, nothing else."""

    username: str
    display_name: str


class Credentials(BaseModel):
    username: str = Field(max_length=64)
    pin: str = Field(max_length=64)


class SetupIn(Credentials):
    display_name: str = Field(default="", max_length=100)


class NewUser(SetupIn):
    role: Role


class UserPatchIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    disabled: bool | None = None
    pin: str | None = Field(default=None, max_length=64)


class NewPin(BaseModel):
    current_pin: str = Field(max_length=64)
    new_pin: str = Field(max_length=64)


# --- sources ---------------------------------------------------------------------------------


class SourceIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    path: str


class SourcePatch(BaseModel):
    enabled: bool | None = None
    label: str | None = Field(default=None, min_length=1, max_length=100)
    owner_id: Id | None = None  # admin: hand a source (and its photos) to another account


class SourceOut(BaseModel):
    id: int
    label: str
    path: str | None  # the folder on the server: admins only (v1.2), else null
    enabled: bool
    kind: str
    owner_id: int | None
    asset_count: int
    problem: str | None = None  # v1.2: "folder not found" when its folder is gone

    @classmethod
    def of(
        cls,
        s: Source,
        asset_count: int,
        show_path: bool,
        problem: str | None = None,
        place: str | None = None,
    ) -> "SourceOut":
        """``place``: what a remote source reads, shown instead of its staging folder."""
        return cls(
            id=s.id,
            label=s.label,
            path=(place or s.root) if show_path else None,
            enabled=s.enabled,
            kind=s.kind,
            owner_id=s.owner_id,
            asset_count=asset_count,
            problem=problem,
        )


LevelName = Literal["view", "download", "edit"]


class UserAccess(BaseModel):
    user_id: Id
    level: LevelName


class Access(BaseModel):
    everyone: LevelName | None
    users: list[UserAccess]


# --- assets ----------------------------------------------------------------------------------


class ImageRef(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None


class PlaceOut(BaseModel):
    country: str
    region: str
    city: str


def image_url(asset_id: int, kind: str, version: int) -> str:
    """Versioned so browsers fetch again after an edit (contract: ``?v=<edit version>``)."""
    return f"/api/assets/{asset_id}/{kind}?v={version}"


class AssetOut(BaseModel):
    id: int
    taken_at: WallClock
    tz_offset_minutes: int | None
    date_source: str
    width: int | None
    height: int | None
    kind: str
    thumb: ImageRef | None
    preview_ready: bool
    favourite: bool
    hidden: bool
    private: bool
    place: PlaceOut | None
    edited: bool
    variant_of: int | None
    group_id: int | None

    @classmethod
    def of(cls, v: AssetView) -> "AssetOut":
        a = v.asset
        width, height = v.display_size or (a.width, a.height)
        thumb = ImageRef(url=image_url(a.id, "thumb", v.edit_version)) if a.thumb_path else None
        p = v.place
        place = PlaceOut(country=p.country, region=p.region, city=p.city) if p else None
        return cls(
            id=a.id,
            taken_at=a.taken_at,
            tz_offset_minutes=a.tz_offset_minutes,
            date_source=a.date_source.value,
            width=width,
            height=height,
            kind=a.kind.value,
            thumb=thumb,
            preview_ready=a.preview_path is not None,
            favourite=v.favourite,
            hidden=v.hidden,
            private=v.private,
            place=place,
            edited=v.edited,
            variant_of=a.variant_of,
            group_id=v.group_id,
        )


class Origin(BaseModel):
    source_id: int
    source_label: str
    relative_path: str


class AlbumRef(BaseModel):
    id: int
    title: str


class AssetDetail(AssetOut):
    byte_size: int
    mime_type: str | None
    camera_make: str | None
    camera_model: str | None
    latitude: float | None
    longitude: float | None
    imported_at: datetime
    origins: list[Origin]
    albums: list[AlbumRef]
    level: LevelName


class AssetPage(BaseModel):
    items: list[AssetOut]
    next_cursor: str | None


class StatePatch(BaseModel):
    favourite: bool | None = None
    hidden: bool | None = None
    private: bool | None = None


Ids = Annotated[list[Id], Field(min_length=1, max_length=10_000)]


class BulkState(BaseModel):
    ids: Ids
    favourite: bool | None = None
    hidden: bool | None = None


class YearCount(BaseModel):
    year: int
    count: int


class SourceCount(BaseModel):
    id: int
    label: str
    count: int


class NameCount(BaseModel):
    name: str
    count: int


class FacetsOut(BaseModel):
    years: list[YearCount]
    sources: list[SourceCount]
    cameras: list[NameCount]
    places: list[NameCount]
    guessed_dates: int
    total: int


class DayCount(BaseModel):
    day: str
    count: int


class MapPoint(BaseModel):
    id: int
    lat: float
    lon: float


class CropIn(BaseModel):
    x: float
    y: float
    w: float
    h: float


class RecipeIO(BaseModel):
    """Contract ``Recipe``. Validation beyond types is the domain's (InvalidRecipeError)."""

    rotate: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    crop: CropIn | None = None
    straighten: float = 0.0

    @classmethod
    def of(cls, recipe: Recipe) -> "RecipeIO":
        return cls.model_validate(recipe.to_dict())


# --- albums ----------------------------------------------------------------------------------


class AlbumIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    asset_ids: list[Id] = Field(default_factory=list, max_length=10_000)


class AlbumPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    cover_asset_id: int | None = None


class AlbumSummary(BaseModel):
    id: int
    title: str
    description: str
    cover: ImageRef | None
    count: int
    owner_id: int
    role: Literal["owner", "editor", "viewer"]
    updated_at: datetime

    @classmethod
    def of(cls, a: AlbumInfo) -> "AlbumSummary":
        cover = a.cover_asset_id
        return cls(
            id=a.id,
            title=a.title,
            description=a.description,
            cover=ImageRef(url=image_url(cover, "thumb", a.cover_version)) if cover else None,
            count=a.count,
            owner_id=a.owner_id,
            role=a.role.value,
            updated_at=a.updated_at,
        )


class AlbumDetail(AlbumSummary):
    items: list[AssetOut]


class AlbumItemsIn(BaseModel):
    asset_ids: Ids
    position: int | None = Field(default=None, ge=0)


class AlbumItemsOut(BaseModel):
    asset_ids: Ids


class AlbumOrder(BaseModel):
    asset_ids: list[Id] = Field(max_length=10_000)


class Member(BaseModel):
    user_id: Id
    role: Literal["viewer", "editor"]


class Counted(BaseModel):
    count: int


# --- downloads -------------------------------------------------------------------------------


class FiltersIn(BaseModel):
    """The /api/assets query filters, as JSON."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    from_day: date | None = Field(default=None, alias="from")
    to_day: date | None = Field(default=None, alias="to")
    year: int | None = None
    month: int | None = None
    source_id: list[Id] = Field(default_factory=list)
    camera: str | None = None
    place: str | None = None
    q: str | None = None
    favourite: bool | None = None
    hidden: bool | None = None
    guessed_date: bool | None = None
    has_location: bool | None = None

    def to_filter(self) -> AssetFilter:
        values = self.model_dump(exclude={"source_id"})
        return AssetFilter(**values, source_ids=tuple(self.source_id))


class DownloadRequest(BaseModel):
    ids: list[Id] | None = Field(default=None, max_length=100_000)
    album_id: Id | None = None
    filters: FiltersIn | None = None
    format: Literal["original", "jpeg", "png", "webp"] = "original"
    quality: int = Field(default=90, ge=1, le=100)
    max_edge: int | None = Field(default=None, ge=1, le=MAX_EDGE)
    strip_location: bool = False
    strip_all_metadata: bool = False
    naming: Naming = Naming.ORIGINAL
    folders: Folders = Folders.FLAT

    def options(self) -> ExportOptions:
        return ExportOptions(
            format=self.format,
            quality=self.quality,
            max_edge=self.max_edge,
            strip_location=self.strip_location,
            strip_all_metadata=self.strip_all_metadata,
            naming=self.naming,
            folders=self.folders,
        )


class Estimate(BaseModel):
    count: int
    bytes: int


# --- dates and trash -------------------------------------------------------------------------


class DatesIn(BaseModel):
    ids: Ids
    set: datetime | None = None  # local wall-clock, no zone
    shift_minutes: int | None = Field(default=None, ge=-60 * 24 * 365 * 200, le=60 * 24 * 365 * 200)


class IdsIn(BaseModel):
    ids: Ids


class OptionalIds(BaseModel):
    ids: list[Id] | None = Field(default=None, max_length=100_000)


class TrashedOut(AssetOut):
    trashed_at: datetime


class Trashed(BaseModel):
    trashed: int


class Restored(BaseModel):
    restored: int


class Purged(BaseModel):
    purged: int


class Updated(BaseModel):
    updated: int


class Queued(BaseModel):
    job_id: int
    source_id: int


class DirectoryEntry(BaseModel):
    """v1.1: who you can share an album with (no usernames, roles or state)."""

    id: int
    display_name: str
