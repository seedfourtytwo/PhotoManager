"""Query-string filters shared by the timeline, facets, calendar and map (contract: Assets)."""

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from photo_assistant.domain.library_filter import AssetFilter, filter_problem


def asset_filter(
    from_day: Annotated[date | None, Query(alias="from")] = None,
    to_day: Annotated[date | None, Query(alias="to")] = None,
    year: int | None = None,
    month: int | None = None,
    source_id: Annotated[list[int] | None, Query()] = None,
    camera: str | None = None,
    place: str | None = None,
    q: str | None = None,
    favourite: bool | None = None,
    hidden: bool | None = None,
    guessed_date: bool | None = None,
    has_location: bool | None = None,
) -> AssetFilter:
    f = AssetFilter(
        from_day=from_day,
        to_day=to_day,
        year=year,
        month=month,
        source_ids=tuple(source_id or ()),
        camera=camera,
        place=place,
        q=q,
        favourite=favourite,
        hidden=hidden,
        guessed_date=guessed_date,
        has_location=has_location,
    )
    return checked(f)


def checked(f: AssetFilter) -> AssetFilter:
    problem = filter_problem(f)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    return f


FilterDep = Annotated[AssetFilter, Depends(asset_filter)]
