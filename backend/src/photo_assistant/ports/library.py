"""Read models for the library as one viewer sees it, plus the ports that app use cases need.

Every read here has already passed the visibility rule (``visible_assets`` in the SQLite
adapter): nothing in these types needs filtering afterwards.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from photo_assistant.domain.access import AlbumRole, Level, Viewer
from photo_assistant.domain.edit_recipe import Recipe, edited_size
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.model import Asset
from photo_assistant.domain.places import Place


@dataclass(frozen=True, slots=True)
class AssetView:
    """One photo as one viewer sees it."""

    asset: Asset
    level: Level
    favourite: bool = False
    hidden: bool = False
    private: bool = False
    owner_id: int | None = None
    place: Place | None = None
    edit_version: int = 0
    edited: bool = False
    group_id: int | None = None
    trashed_at: datetime | None = None
    recipe: Recipe | None = None

    @property
    def display_size(self) -> tuple[int, int] | None:
        """Width and height as shown: after the edit recipe, if any."""
        a = self.asset
        if a.width is None or a.height is None:
            return None
        if self.recipe is None:
            return a.width, a.height
        return edited_size(a.width, a.height, self.recipe)

    @property
    def id(self) -> int:
        return self.asset.id


@dataclass(frozen=True, slots=True)
class ViewPage:
    items: list[AssetView]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Count:
    key: str
    count: int
    label: str = ""


@dataclass(frozen=True, slots=True)
class Facets:
    years: list[Count]
    sources: list[Count]  # key = source id, label = source label
    cameras: list[Count]
    places: list[Count]
    guessed_dates: int
    total: int


@dataclass(frozen=True, slots=True)
class AlbumInfo:
    id: int
    owner_id: int
    title: str
    description: str
    cover_asset_id: int | None  # the chosen cover if you may see it, else the first photo
    cover_version: int  # edit version of the cover (for its thumbnail URL)
    count: int  # photos you can see
    role: AlbumRole
    updated_at: datetime


class LibraryReader(Protocol):
    """What use cases read: always on behalf of a viewer, never unfiltered."""

    def views_by_ids(self, viewer: Viewer, ids: Sequence[int]) -> list[AssetView]:
        """The visible ones among ``ids``, in the given order (unknown/hidden ids dropped)."""
        ...

    def list_all_views(self, viewer: Viewer, f: AssetFilter) -> list[AssetView]: ...

    def album_views(self, viewer: Viewer, album_id: int) -> list[AssetView]: ...

    def first_origin_name(self, asset_id: int) -> str | None:
        """File name the photo had in the first source it came from."""
        ...
