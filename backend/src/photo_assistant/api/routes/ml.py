"""Local ML over HTTP (docs/contracts/api-v1.md): search, similar photos, faces, tags, people.

Every route starts from the visibility rule. Search hands the use cases the ids left after
its filters (``repo.visible_asset_ids``); people and similar photos hand them the viewer, and
the ML store applies the same rule inside its own queries. The use cases only rank or filter
inside that; anything outside is a 404. Without model files every route still answers: search
falls back to the core text search and says why.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from photo_assistant.api.deps import (
    ADMIN_ONLY,
    LOGGED_IN,
    ServicesDep,
    ViewerDep,
    member_user,
    require_view,
)
from photo_assistant.api.filters import FilterDep
from photo_assistant.api.library_scopes import facet_candidates, matching_words, named_photos
from photo_assistant.api.routes.assets import IMMUTABLE
from photo_assistant.api.schemas import AssetOut, Id
from photo_assistant.api.services import Services
from photo_assistant.app.portraits import portrait_version
from photo_assistant.app.search import NotIndexedError, SearchUnavailableError
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.faces import Circle
from photo_assistant.ports.ml import PersonSummary, Portrait, StoredFace

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


class PortraitOut(BaseModel):
    """A round picture: a circle on photo ``asset_id`` as displayed, without its edits."""

    face_id: int
    asset_id: int
    cx: float  # the centre, as fractions of the photo's width and height
    cy: float
    size: float  # the square round it, as a fraction of the photo's shorter edge
    chosen: bool  # by a person; false: the automatic circle round the face
    url: str  # the picture itself; it changes whenever the picture does

    @classmethod
    def of(cls, p: Portrait, path: str) -> "PortraitOut":
        return cls(
            face_id=p.face.id,
            asset_id=p.face.asset_id,
            cx=p.circle.cx,
            cy=p.circle.cy,
            size=p.circle.size,
            chosen=p.chosen,
            url=f"{path}?v={portrait_version(p)}",
        )


class PersonOut(BaseModel):
    id: int
    name: str | None
    face_count: int
    asset_count: int
    hidden: bool  # left out of GET /people unless asked for
    cover: FaceOut | None  # the face the portrait is of
    portrait: PortraitOut | None  # as this viewer gets it: only from a photo they may see

    @classmethod
    def of(cls, p: PersonSummary) -> "PersonOut":
        cover = FaceOut.of(p.cover_face) if p.cover_face else None
        path = f"/api/people/{p.id}/portrait"
        return cls(
            id=p.id,
            name=p.name,
            face_count=p.face_count,
            asset_count=p.asset_count,
            hidden=p.hidden,
            cover=cover,
            portrait=PortraitOut.of(p.portrait, path) if p.portrait else None,
        )


class PortraitIn(BaseModel):
    """Numbers outside the photo are brought inside it, not refused."""

    face_id: Id
    cx: float
    cy: float
    size: float


class PersonPatch(BaseModel):
    """Only what is sent changes. ``name: null`` takes the name away."""

    name: str | None = None
    hidden: bool | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "PersonPatch":
        if not self.model_fields_set:
            raise ValueError("nothing to change: send name or hidden")
        return self


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


def _clip_ready(services: Services) -> bool:
    return services.ml.clip.status().ready


def _scored(
    services: Services, viewer: Viewer, ids: list[int], scores: dict[int, float] | None = None
) -> list[ScoredAssetOut]:
    views = services.repo.views_by_ids(viewer, ids)
    return [
        ScoredAssetOut(**AssetOut.of(v).model_dump(), score=(scores or {}).get(v.id)) for v in views
    ]


def _by_meaning(
    services: Services, text: str, candidates: list[int], named: list[int], limit: int
) -> tuple[list[int], dict[int, float]]:
    """The photos the words name (an album, a tag) first, ranked by meaning, then the closest
    others. A named photo not analysed yet still comes, after the ranked ones, without a score."""
    first = services.ml.search(text, named, len(named)) if named else []
    scores = {h.asset_id: h.score for h in first}
    order = list(scores) + [i for i in named if i not in scores]
    shown = set(order)
    for hit in services.ml.search(text, candidates, limit):
        if hit.asset_id not in shown:
            order.append(hit.asset_id)
            scores[hit.asset_id] = hit.score
    return order[:limit], scores


# --- search ----------------------------------------------------------------------------------


@router.get("/search")
def search(
    services: ServicesDep,
    viewer: ViewerDep,
    f: FilterDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> SearchOut:
    """``q`` as on the timeline, plus facets (``date:2023 person:Lea tag:beach place:… camera:…``).
    People and places named in the words narrow like their facets. Free text is ranked by CLIP
    when the model is installed, photos in a named album or with a named tag first; else
    matched as words."""
    parsed, narrowed, candidates = facet_candidates(services.repo, services.ml, viewer, f)
    facets = [FacetOut(name=k, value=v) for k, v in parsed.facets]
    text = parsed.text

    def out(items: list[ScoredAssetOut], mode: str, detail: str | None = None) -> SearchOut:
        return SearchOut(items=items, text=text, facets=facets, mode=mode, detail=detail)

    if not text:
        return out(_scored(services, viewer, candidates[:limit]), "filter")
    if _clip_ready(services):
        named = named_photos(services.repo, services.ml, viewer, text, candidates)
        try:
            ids, scores = _by_meaning(services, text, candidates, named, limit)
        except SearchUnavailableError as exc:
            detail = f"{MODELS_MISSING} ({exc})"
        else:
            return out(_scored(services, viewer, ids, scores), "semantic")
    else:
        detail = MODELS_MISSING
    matching = matching_words(services.repo, viewer, narrowed, text)
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
        hits = services.ml.similar(asset_id, viewer, limit)
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
def list_people(services: ServicesDep, viewer: ViewerDep, hidden: bool = False) -> list[PersonOut]:
    """The people listed in People; ``?hidden=true`` the ones hidden from it instead."""
    return [PersonOut.of(p) for p in services.ml.people.list_all(viewer, hidden=hidden)]


@router.get("/people/{person_id}")
def get_person(services: ServicesDep, viewer: ViewerDep, person_id: int) -> PersonOut:
    return PersonOut.of(services.ml.people.get(person_id, viewer))


@router.patch("/people/{person_id}", dependencies=NOT_GUEST)
def change_person(
    services: ServicesDep, viewer: ViewerDep, person_id: int, body: PersonPatch
) -> PersonOut:
    people = services.ml.people
    person = people.get(person_id, viewer)
    if "name" in body.model_fields_set:
        person = people.rename(person_id, body.name, viewer)
    if body.hidden is not None:
        person = people.set_hidden(person_id, body.hidden, viewer)
    return PersonOut.of(person)


def _serve_portrait(services: Services, portrait: Portrait, v: str | None) -> Response:
    """Kept by the browser for good only at the address of this very picture."""
    cache = IMMUTABLE if v == portrait_version(portrait) else "no-store"
    path = services.ml.portraits.image(portrait)
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": cache})


@router.get("/people/{person_id}/portrait")
def person_portrait(
    services: ServicesDep, viewer: ViewerDep, person_id: int, v: str | None = None
) -> Response:
    """The person's round picture (WebP, at most 320 px), as this viewer gets it."""
    return _serve_portrait(services, services.ml.portraits.of_person(person_id, viewer), v)


@router.put("/people/{person_id}/portrait", dependencies=NOT_GUEST)
def choose_portrait(
    services: ServicesDep, viewer: ViewerDep, person_id: int, body: PortraitIn
) -> PersonOut:
    circle = Circle(body.cx, body.cy, body.size)
    return PersonOut.of(services.ml.portraits.choose(person_id, body.face_id, circle, viewer))


@router.delete("/people/{person_id}/portrait", dependencies=NOT_GUEST)
def use_automatic_portrait(services: ServicesDep, viewer: ViewerDep, person_id: int) -> PersonOut:
    return PersonOut.of(services.ml.portraits.use_automatic(person_id, viewer))


@router.get("/people/{person_id}/faces")
def person_faces(
    services: ServicesDep,
    viewer: ViewerDep,
    person_id: int,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
) -> list[PortraitOut]:
    """The faces a portrait can be chosen from, the best first, each as its automatic
    portrait."""
    found = services.ml.portraits.candidates(person_id, viewer, limit)
    return [PortraitOut.of(p, f"/api/faces/{p.face.id}/portrait") for p in found]


@router.get("/faces/{face_id}/portrait")
def face_portrait(
    services: ServicesDep, viewer: ViewerDep, face_id: int, v: str | None = None
) -> Response:
    """The automatic round picture of one face; ``404`` unless you may see its photo."""
    return _serve_portrait(services, services.ml.portraits.of_face(face_id, viewer), v)


@router.post("/people/{person_id}/merge", dependencies=NOT_GUEST)
def merge_people(
    services: ServicesDep, viewer: ViewerDep, person_id: int, body: MergeIn
) -> PersonOut:
    person = services.ml.people.merge(person_id, body.source_ids, viewer)
    return PersonOut.of(person)


@router.post("/people/split", dependencies=NOT_GUEST)
def split_people(services: ServicesDep, viewer: ViewerDep, body: SplitIn) -> PersonOut:
    person = services.ml.people.split(
        body.face_ids, viewer, person_id=body.person_id, name=body.name
    )
    return PersonOut.of(person)


@router.get("/people/{person_id}/assets")
def person_assets(
    services: ServicesDep,
    viewer: ViewerDep,
    person_id: int,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    cursor: str | None = None,
) -> PersonAssets:
    ordered = services.ml.people.assets(person_id, viewer)  # timeline order, newest first
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
