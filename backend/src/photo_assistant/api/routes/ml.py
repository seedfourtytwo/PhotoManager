"""Local ML over HTTP (docs/wiring/ml.md): search, similar photos, faces, tags, people.

Every route starts from the visibility rule (``repo.visible_asset_ids``) and hands that set to
the use cases, which only rank or filter inside it; anything outside is a 404. Without model
files every route still answers: search falls back to the core text search and says why.
"""

from collections.abc import Collection
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from photo_assistant.api.deps import (
    ADMIN_ONLY,
    LOGGED_IN,
    ServicesDep,
    ViewerDep,
    member_user,
    require_view,
)
from photo_assistant.api.filters import FilterDep, checked
from photo_assistant.api.schemas import AssetOut, Id
from photo_assistant.api.services import Services
from photo_assistant.app.people import FaceNotFoundError, PersonNotFoundError
from photo_assistant.app.search import NotIndexedError, SearchUnavailableError, parse_query
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.search_query import InvalidFacetError, ParsedQuery, with_facets
from photo_assistant.ports.ml import PersonSummary, StoredFace

router = APIRouter(prefix="/api", tags=["ml"], dependencies=LOGGED_IN)

MODELS_MISSING = "models not installed: run `just models` on this machine"


# --- schemas ---------------------------------------------------------------------------------


class ScoredAssetOut(AssetOut):
    score: float | None  # cosine similarity for semantic hits; None otherwise


class FacetOut(BaseModel):
    name: str
    value: str


class SearchOut(BaseModel):
    items: list[ScoredAssetOut]
    text: str  # the free text left after the facets
    facets: list[FacetOut]
    mode: str  # semantic | text (fallback) | filter (facets only)
    detail: str | None  # why the search fell back, if it did


class BoxOut(BaseModel):
    x: float
    y: float
    w: float
    h: float


class FaceOut(BaseModel):
    id: int
    asset_id: int
    box: BoxOut
    score: float
    person_id: int | None

    @classmethod
    def of(cls, f: StoredFace) -> "FaceOut":
        b = f.box
        return cls(
            id=f.id,
            asset_id=f.asset_id,
            box=BoxOut(x=b.x, y=b.y, w=b.width, h=b.height),
            score=f.score,
            person_id=f.person_id,
        )


class TagOut(BaseModel):
    name: str
    score: float


class TagsOut(BaseModel):
    tags: list[TagOut]
    screen_or_document: bool | None


class PersonOut(BaseModel):
    id: int
    name: str | None
    face_count: int
    asset_count: int
    cover: FaceOut | None  # crop the asset's thumbnail to this box for the People grid

    @classmethod
    def of(cls, p: PersonSummary) -> "PersonOut":
        cover = FaceOut.of(p.cover_face) if p.cover_face else None
        return cls(
            id=p.id,
            name=p.name,
            face_count=p.face_count,
            asset_count=p.asset_count,
            cover=cover,
        )


class PersonPatch(BaseModel):
    name: str | None


class MergeIn(BaseModel):
    source_ids: list[Id] = Field(min_length=1)


class SplitIn(BaseModel):
    face_ids: list[Id]
    person_id: Id | None = None
    name: str | None = None


class PersonAssets(BaseModel):
    items: list[AssetOut]
    next_cursor: str | None


class ModelOut(BaseModel):
    ready: bool
    detail: str


class MlStatusOut(BaseModel):
    clip: ModelOut
    faces: ModelOut
    models_installed: bool
    counts: dict[str, dict[str, int]]


class BackfillOut(BaseModel):
    queued: int
    detail: str | None


# --- helpers ---------------------------------------------------------------------------------


# Naming and regrouping people changes what others see: members and admins only.
NOT_GUEST = [Depends(member_user)]


def _visible(services: Services, viewer: Viewer) -> list[int]:
    return services.repo.visible_asset_ids(viewer)


def _clip_ready(services: Services) -> bool:
    return services.ml.clip.status().ready


def _person_ids_named(services: Services, name: str, visible: Collection[int]) -> set[int]:
    wanted = name.casefold()
    people = services.ml.people.list_all(visible)
    return {p.id for p in people if p.name is not None and p.name.casefold() == wanted}


def _narrow_by_people_and_tags(
    services: Services, parsed: ParsedQuery, candidates: list[int]
) -> list[int]:
    keep = set(candidates)
    for name in parsed.values("person"):
        found: set[int] = set()
        for person_id in _person_ids_named(services, name, keep):
            found |= set(services.ml.people.assets(person_id, keep))
        keep &= found
    for tag in parsed.values("tag"):
        keep &= set(services.ml.store.asset_ids_with_tag(tag, keep))
    return [i for i in candidates if i in keep]  # keep the timeline order


def _scored(
    services: Services, viewer: Viewer, ids: list[int], scores: dict[int, float] | None = None
) -> list[ScoredAssetOut]:
    views = services.repo.views_by_ids(viewer, ids)
    return [
        ScoredAssetOut(**AssetOut.of(v).model_dump(), score=(scores or {}).get(v.id)) for v in views
    ]


def _person_or_404(exc: LookupError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# --- search ----------------------------------------------------------------------------------


@router.get("/search")
def search(
    services: ServicesDep,
    viewer: ViewerDep,
    f: FilterDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> SearchOut:
    """``q`` as on the timeline, plus facets (``date:2023 person:Lea tag:beach place:… camera:…``).
    Free text is ranked by CLIP when the model is installed, else matched as words."""
    parsed = parse_query(f.q or "")
    try:
        narrowed = checked(with_facets(replace(f, q=None), parsed))
    except InvalidFacetError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    candidates = services.repo.visible_asset_ids(viewer, narrowed)
    candidates = _narrow_by_people_and_tags(services, parsed, candidates)
    facets = [FacetOut(name=k, value=v) for k, v in parsed.facets]
    text = parsed.text

    def out(items: list[ScoredAssetOut], mode: str, detail: str | None = None) -> SearchOut:
        return SearchOut(items=items, text=text, facets=facets, mode=mode, detail=detail)

    if not text:
        return out(_scored(services, viewer, candidates[:limit]), "filter")
    if _clip_ready(services):
        try:
            hits = services.ml.search(text, candidates, limit)
        except SearchUnavailableError as exc:
            detail = f"{MODELS_MISSING} ({exc})"
        else:
            scores = {h.asset_id: h.score for h in hits}
            return out(_scored(services, viewer, list(scores), scores), "semantic")
    else:
        detail = MODELS_MISSING
    matching = set(services.repo.visible_asset_ids(viewer, checked(replace(narrowed, q=text))))
    ids = [i for i in candidates if i in matching][:limit]
    return out(_scored(services, viewer, ids), "text", detail)


@router.get("/assets/{asset_id}/similar")
def similar(
    services: ServicesDep,
    viewer: ViewerDep,
    asset_id: int,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ScoredAssetOut]:
    require_view(services, viewer, asset_id)
    if not _clip_ready(services):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MODELS_MISSING)
    try:
        hits = services.ml.similar(asset_id, _visible(services, viewer), limit)
    except NotIndexedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this photo has not been analysed yet"
        ) from exc
    scores = {h.asset_id: h.score for h in hits}
    return _scored(services, viewer, list(scores), scores)


@router.get("/assets/{asset_id}/faces")
def faces(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> list[FaceOut]:
    require_view(services, viewer, asset_id)
    found = services.ml.people.faces_of_asset(asset_id, {asset_id})
    return [FaceOut.of(f) for f in found]


@router.get("/assets/{asset_id}/tags")
def tags(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> TagsOut:
    require_view(services, viewer, asset_id)
    store = services.ml.store
    return TagsOut(
        tags=[TagOut(name=t.name, score=t.score) for t in store.tags_of(asset_id)],
        screen_or_document=store.is_screen_or_document(asset_id),
    )


# --- people ----------------------------------------------------------------------------------


@router.get("/people")
def list_people(services: ServicesDep, viewer: ViewerDep) -> list[PersonOut]:
    return [PersonOut.of(p) for p in services.ml.people.list_all(_visible(services, viewer))]


@router.get("/people/{person_id}")
def get_person(services: ServicesDep, viewer: ViewerDep, person_id: int) -> PersonOut:
    try:
        return PersonOut.of(services.ml.people.get(person_id, _visible(services, viewer)))
    except PersonNotFoundError as exc:
        raise _person_or_404(exc) from exc


@router.patch("/people/{person_id}", dependencies=NOT_GUEST)
def rename_person(
    services: ServicesDep, viewer: ViewerDep, person_id: int, body: PersonPatch
) -> PersonOut:
    try:
        person = services.ml.people.rename(person_id, body.name, _visible(services, viewer))
    except PersonNotFoundError as exc:
        raise _person_or_404(exc) from exc
    return PersonOut.of(person)


@router.post("/people/{person_id}/merge", dependencies=NOT_GUEST)
def merge_people(
    services: ServicesDep, viewer: ViewerDep, person_id: int, body: MergeIn
) -> PersonOut:
    try:
        person = services.ml.people.merge(person_id, body.source_ids, _visible(services, viewer))
    except PersonNotFoundError as exc:
        raise _person_or_404(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return PersonOut.of(person)


@router.post("/people/split", dependencies=NOT_GUEST)
def split_people(services: ServicesDep, viewer: ViewerDep, body: SplitIn) -> PersonOut:
    try:
        person = services.ml.people.split(
            body.face_ids, _visible(services, viewer), person_id=body.person_id, name=body.name
        )
    except (PersonNotFoundError, FaceNotFoundError) as exc:
        raise _person_or_404(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return PersonOut.of(person)


@router.get("/people/{person_id}/assets")
def person_assets(
    services: ServicesDep,
    viewer: ViewerDep,
    person_id: int,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    cursor: str | None = None,
) -> PersonAssets:
    visible = _visible(services, viewer)
    try:
        ids = set(services.ml.people.assets(person_id, visible))
    except PersonNotFoundError as exc:
        raise _person_or_404(exc) from exc
    ordered = [i for i in visible if i in ids]  # timeline order, newest first
    start = int(cursor) if cursor and cursor.isdigit() else 0
    page = ordered[start : start + limit]
    more = start + limit < len(ordered)
    views = services.repo.views_by_ids(viewer, page)
    return PersonAssets(
        items=[AssetOut.of(v) for v in views], next_cursor=str(start + limit) if more else None
    )


# --- status and backfill ---------------------------------------------------------------------


@router.get("/ml/status")
def ml_status(services: ServicesDep) -> MlStatusOut:
    found = services.ml.status()
    clip, face = found["clip"], found["faces"]
    return MlStatusOut(
        clip=ModelOut(ready=clip.ready, detail=clip.detail),
        faces=ModelOut(ready=face.ready, detail=face.detail),
        models_installed=clip.ready and face.ready,
        counts=services.ml.store.task_counts(),
    )


@router.post("/ml/backfill", dependencies=ADMIN_ONLY)
def ml_backfill(services: ServicesDep) -> BackfillOut:
    """Queue every photo not analysed yet (run once after `just models`)."""
    found = services.ml.status()
    ready = all(s.ready for s in found.values())
    return BackfillOut(queued=services.ml.backfill(), detail=None if ready else MODELS_MISSING)
