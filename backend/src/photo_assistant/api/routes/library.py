"""Whole-library views: the calendar heat map and the map (contract: Assets)."""

from fastapi import APIRouter

from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep
from photo_assistant.api.filters import FilterDep
from photo_assistant.api.schemas import DayCount, MapPoint

router = APIRouter(prefix="/api", tags=["library"], dependencies=LOGGED_IN)


@router.get("/calendar")
def calendar(services: ServicesDep, viewer: ViewerDep, f: FilterDep) -> list[DayCount]:
    return [DayCount(day=c.key, count=c.count) for c in services.repo.calendar(viewer, f)]


@router.get("/map")
def map_points(services: ServicesDep, viewer: ViewerDep, f: FilterDep) -> list[MapPoint]:
    return [MapPoint(id=i, lat=lat, lon=lon) for i, lat, lon in services.repo.map_points(viewer, f)]
