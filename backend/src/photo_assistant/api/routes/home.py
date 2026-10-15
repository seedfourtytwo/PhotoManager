"""Home (issue 54): on this day, photos to rediscover, memories, the years and what is new, for
the signed-in account."""

from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep
from photo_assistant.api.schemas import AssetOut, SourceCount
from photo_assistant.app.home import HomePage, home_page
from photo_assistant.domain.memories import Memory

router = APIRouter(prefix="/api", tags=["home"], dependencies=LOGGED_IN)


class HomeFilter(BaseModel):
    """The ``/api/assets`` filters that list exactly the photos a block counts."""

    from_day: date = Field(serialization_alias="from")
    to_day: date = Field(serialization_alias="to")
    guessed_date: Literal[False] = False  # Home leaves out dates guessed from a file's mtime


class PersonRef(BaseModel):
    id: int
    name: str


class OnThisDayOut(BaseModel):
    day: date  # today's date in that year
    years_ago: int
    exact: bool  # false: no photo on the day itself, so three days either side
    count: int
    cover: AssetOut
    place: str | None
    people: list[PersonRef]
    filter: HomeFilter


class MemoryOut(BaseModel):
    key: str
    title: str
    from_day: date = Field(serialization_alias="from")
    to_day: date = Field(serialization_alias="to")
    count: int
    cover: AssetOut
    filter: HomeFilter


class NewOut(BaseModel):
    count: int
    days: int
    sources: list[SourceCount]
    items: list[AssetOut]  # the newest arrivals, newest first


class HomeOut(BaseModel):
    on_this_day: OnThisDayOut | None
    rediscover: list[AssetOut]  # the one to show large first
    memories: list[MemoryOut]
    years: list[MemoryOut]  # a memory each: the whole year
    new: NewOut


def _memory_out(m: Memory, shown: dict[int, AssetOut]) -> MemoryOut:
    return MemoryOut(
        key=m.key,
        title=m.title,
        from_day=m.first_day,
        to_day=m.last_day,
        count=m.count,
        cover=shown[m.cover_id],
        filter=HomeFilter(from_day=m.first_day, to_day=m.last_day),
    )


def _home_out(page: HomePage) -> HomeOut:
    shown = {asset_id: AssetOut.of(view) for asset_id, view in page.views.items()}
    day = page.on_this_day
    return HomeOut(
        on_this_day=None
        if day is None
        else OnThisDayOut(
            day=day.day,
            years_ago=day.years_ago,
            exact=day.exact,
            count=day.count,
            cover=shown[day.cover_id],
            place=day.place,
            people=[PersonRef(id=i, name=n) for i, n in page.people],
            filter=HomeFilter(from_day=day.first_day, to_day=day.last_day),
        ),
        rediscover=[shown[i] for i in page.rediscover if i in shown],
        memories=[_memory_out(m, shown) for m in page.memories],
        years=[_memory_out(m, shown) for m in page.years],
        new=NewOut(
            count=page.arrivals.count,
            days=page.days,
            sources=[
                SourceCount(id=int(c.key), label=c.label, count=c.count)
                for c in page.arrivals.sources
            ],
            items=[shown[i] for i in page.arrivals.newest if i in shown],
        ),
    )


@router.get("/home")
def home(services: ServicesDep, viewer: ViewerDep) -> HomeOut:
    page = home_page(services.repo, services.ml.people, viewer, services.clock.now())
    return _home_out(page)
