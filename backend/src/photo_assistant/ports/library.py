"""Read models for the library as one viewer sees it, plus the ports that app use cases need.

Every read here has already passed the visibility rule (``visible_assets`` in the SQLite
adapter): nothing in these types needs filtering afterwards.
"""

from dataclasses import dataclass
from datetime import datetime

from photo_assistant.domain.access import AlbumRole, Level
from photo_assistant.domain.edit_recipe import Recipe, edited_size
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
    place: Place | None = None
    edit_version: int = 0
    edited: bool = False
    group_id: int | None = None
    trashed_at: datetime | None = None
    held_reason: str | None = None  # waiting for review (issue 8): why
    held_like: int | None = None  # a look-alike: the library photo it resembles
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
