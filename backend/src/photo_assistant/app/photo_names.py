"""The names of photos as one viewer reads them: shown, and given to what they download."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.display_name import Dated, display_names
from photo_assistant.ports.library import AssetView


class NameStore(Protocol):
    def first_origin_names(self, viewer: Viewer, asset_ids: Sequence[int]) -> dict[int, str]: ...

    def minute_mates(self, viewer: Viewer, asset_ids: Sequence[int]) -> list[Dated]: ...


@dataclass(frozen=True, slots=True)
class PhotoName:
    shown: str  # the display name, without an extension
    original: str | None  # the file name in its first source the viewer sees; None: none


def photo_names(
    store: NameStore, viewer: Viewer, views: Sequence[AssetView]
) -> dict[int, PhotoName]:
    """Two queries for any number of photos."""
    ids = [v.id for v in views]
    originals = store.first_origin_names(viewer, ids)
    dated = [Dated(v.id, v.asset.taken_at, v.asset.date_source) for v in views]
    shown = display_names(dated, store.minute_mates(viewer, ids), originals)
    return {i: PhotoName(shown[i], originals.get(i)) for i in ids}
