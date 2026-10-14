"""Home (issue 54) for one viewer: on this day and who is on it, memories, what is new.

Everything is read through the viewer's own access, so Home never shows a photo, a person or a
folder the timeline would not. "Today" is the server's local date at ``now``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from photo_assistant.domain.access import Viewer
from photo_assistant.domain.memories import Memory, Moment, memories
from photo_assistant.domain.on_this_day import OnThisDay, on_this_day
from photo_assistant.ports.library import Arrivals, AssetView
from photo_assistant.ports.ml import PersonSummary, Visible

NEW_DAYS = 7  # "new this week": photos imported in the last seven days
NEW_SHOWN = 12  # of those, the newest arrivals Home shows


class HomeStore(Protocol):
    def moments(self, viewer: Viewer) -> list[Moment]:
        """The photos with a real date this viewer sees on the timeline, in time order."""
        ...

    def arrivals(self, viewer: Viewer, since: datetime, limit: int) -> Arrivals: ...
    def views_by_ids(self, viewer: Viewer, ids: Sequence[int]) -> list[AssetView]: ...


class PeopleOnPhotos(Protocol):
    def list_all(self, visible: Visible, *, hidden: bool | None = False) -> list[PersonSummary]:
        """The listed people with a face on ``visible`` photos, named first, most photos first."""
        ...


@dataclass(frozen=True, slots=True)
class HomePage:
    on_this_day: OnThisDay | None
    people: list[tuple[int, str]]  # the named, listed people on the on-this-day photos
    memories: list[Memory]
    arrivals: Arrivals
    days: int  # how far back arrivals look
    views: dict[int, AssetView]  # every photo the page shows: covers and newest arrivals


def home_page(store: HomeStore, people: PeopleOnPhotos, viewer: Viewer, now: datetime) -> HomePage:
    today = now.astimezone().date()
    moments = store.moments(viewer)
    day = on_this_day(moments, today)
    found = memories(moments, today)
    arrivals = store.arrivals(viewer, now - timedelta(days=NEW_DAYS), NEW_SHOWN)
    shown = [m.cover_id for m in found] + arrivals.newest + ([day.cover_id] if day else [])
    on_it = [] if day is None else people.list_all([m.asset_id for m in day.photos])
    return HomePage(
        on_this_day=day,
        people=[(p.id, p.name) for p in on_it if p.name],
        memories=found,
        arrivals=arrivals,
        days=NEW_DAYS,
        views={v.id: v for v in store.views_by_ids(viewer, shown)},
    )
