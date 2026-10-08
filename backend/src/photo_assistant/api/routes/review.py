"""To review (issue 8): photos held out of the library until someone keeps or discards them."""

from fastapi import APIRouter
from pydantic import BaseModel

from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep, require_views
from photo_assistant.api.schemas import AssetOut, IdsIn
from photo_assistant.app.enrich import FULL_REGROUP, GROUP_JOB
from photo_assistant.domain.access import Level
from photo_assistant.domain.review import LOOKALIKE

router = APIRouter(prefix="/api/review", tags=["review"], dependencies=LOGGED_IN)


class HeldOut(BaseModel):
    asset: AssetOut
    like: AssetOut | None  # a look-alike: the library photo it resembles, if you may see it


class ReviewGroup(BaseModel):
    reason: str  # "lookalike", or the kind of clutter ("screenshot", "document", ...)
    items: list[HeldOut]


class ReviewOut(BaseModel):
    count: int
    groups: list[ReviewGroup]


class ReviewCount(BaseModel):
    count: int


class Kept(BaseModel):
    kept: int


class Discarded(BaseModel):
    discarded: int


@router.get("")
def waiting(services: ServicesDep, viewer: ViewerDep) -> ReviewOut:
    """What waits for you, grouped by reason: look-alikes first, then each kind of clutter."""
    held = services.review.waiting(viewer)
    likes = [v.held_like for v in held if v.held_like is not None]
    like_of = {v.id: v for v in services.repo.views_by_ids(viewer, likes)}
    groups: dict[str, list[HeldOut]] = {}
    for view in held:
        like = like_of.get(view.held_like) if view.held_like is not None else None
        item = HeldOut(asset=AssetOut.of(view), like=AssetOut.of(like) if like else None)
        groups.setdefault(view.held_reason or "", []).append(item)
    ordered = sorted(groups, key=lambda reason: (reason != LOOKALIKE, reason))
    return ReviewOut(
        count=len(held), groups=[ReviewGroup(reason=r, items=groups[r]) for r in ordered]
    )


@router.get("/count")
def count(services: ServicesDep, viewer: ViewerDep) -> ReviewCount:
    return ReviewCount(count=services.review.count(viewer))


@router.post("/keep")
def keep(services: ServicesDep, viewer: ViewerDep, body: IdsIn) -> Kept:
    """These photos join the library and are never held again (needs edit on every one)."""
    require_views(services, viewer, body.ids, Level.EDIT, held=True)
    kept = services.review.keep(body.ids)
    services.repo.enqueue_once(GROUP_JOB, FULL_REGROUP)  # groups gain members
    return Kept(kept=kept)


@router.post("/discard")
def discard(services: ServicesDep, viewer: ViewerDep, body: IdsIn) -> Discarded:
    """These photos go to the 30-day trash (needs edit on every one). Sources are never
    touched."""
    require_views(services, viewer, body.ids, Level.EDIT, held=True)
    return Discarded(discarded=services.review.discard(body.ids, viewer.user_id))
