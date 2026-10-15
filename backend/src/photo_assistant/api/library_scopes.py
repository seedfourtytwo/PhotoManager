"""What a filter, an album or a person holds for one viewer, answered as the screens answer it.

Search (``routes/ml.py``) and "Keep on my phone" (``LibraryScopes``, the ``SyncScopes`` of
``app/device_sync.py``) share this, so a kept filter holds what the same words show on screen.
Everything starts from the repository's visibility rule; nothing here widens it.
"""

from dataclasses import replace

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.api.filters import checked
from photo_assistant.api.ml_services import MlServices
from photo_assistant.api.schemas import FiltersIn
from photo_assistant.app.people import PersonNotFoundError
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.device_sync import SyncKind, SyncTarget
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.search_query import (
    ParsedQuery,
    name_key,
    parse_query,
    spot_names,
    with_facets,
)
from photo_assistant.domain.tags import VOCABULARY
from photo_assistant.ports.device_sync import Resolved


def _person_ids_named(ml: MlServices, name: str, visible: set[int]) -> set[int]:
    wanted = name_key(name)
    people = ml.people.list_all(visible, hidden=None)  # hidden is not forgotten
    return {p.id for p in people if p.name is not None and name_key(p.name) == wanted}


def _who_and_where(
    repo: SqliteRepository, ml: MlServices, viewer: Viewer, parsed: ParsedQuery
) -> ParsedQuery:
    """People and places named in the plain words become facets: CLIP cannot see who or where."""
    if not parsed.text:
        return parsed
    people = [p.name for p in ml.people.list_all(viewer, hidden=None) if p.name]
    places = [c.key for c in repo.facets(viewer, AssetFilter()).places]
    spotted = spot_names(parsed.text, {"person": people, "place": places})
    return ParsedQuery(spotted.text, parsed.facets + spotted.names)


def _narrow_by_people_and_tags(
    ml: MlServices, parsed: ParsedQuery, candidates: list[int]
) -> list[int]:
    keep = set(candidates)
    for name in parsed.values("person"):
        found: set[int] = set()
        for person_id in _person_ids_named(ml, name, keep):
            found |= set(ml.people.assets(person_id, keep))
        keep &= found
    for tag in parsed.values("tag"):
        keep &= set(ml.store.asset_ids_with_tag(tag, keep))
    return [i for i in candidates if i in keep]  # keep the timeline order


def facet_candidates(
    repo: SqliteRepository, ml: MlServices, viewer: Viewer, f: AssetFilter
) -> tuple[ParsedQuery, AssetFilter, list[int]]:
    """The facets of ``f.q`` (date, place, camera, person, tag, and the people and places its
    words name) applied over the filters: the parsed words, the filter they made, and the
    visible ids left, newest first."""
    parsed = _who_and_where(repo, ml, viewer, parse_query(f.q or ""))
    narrowed = checked(with_facets(replace(f, q=None), parsed))
    candidates = repo.visible_asset_ids(viewer, narrowed)
    return parsed, narrowed, _narrow_by_people_and_tags(ml, parsed, candidates)


def named_photos(
    repo: SqliteRepository, ml: MlServices, viewer: Viewer, text: str, candidates: list[int]
) -> list[int]:
    """The candidates in an album, or with a tag, that the words name, newest first."""
    albums = repo.list_albums(viewer)
    tags = [t.name for t in VOCABULARY]
    spotted = spot_names(text, {"album": [a.title for a in albums], "tag": tags})
    keep = set(candidates)
    named: set[int] = set()
    for kind, name in spotted.names:
        if kind == "tag":
            named.update(ml.store.asset_ids_with_tag(name, keep))
            continue
        for album in albums:
            if name_key(album.title) == name_key(name):
                named.update(repo.album_asset_ids(album.id))
    return [i for i in candidates if i in named]


def matching_words(
    repo: SqliteRepository, viewer: Viewer, narrowed: AssetFilter, text: str
) -> set[int]:
    """The ids where every word matches (file name, place, camera, album title)."""
    return set(repo.visible_asset_ids(viewer, checked(replace(narrowed, q=text))))


def filter_ids(repo: SqliteRepository, ml: MlServices, viewer: Viewer, f: AssetFilter) -> list[int]:
    """Every photo the filter names, as search names them when it does not rank by meaning:
    facets narrow, then every remaining word must match."""
    parsed, narrowed, candidates = facet_candidates(repo, ml, viewer, f)
    if not parsed.text:
        return candidates
    matching = matching_words(repo, viewer, narrowed, parsed.text)
    return [i for i in candidates if i in matching]


class LibraryScopes:
    """``SyncScopes`` over the library: an album, a person or filters, for one viewer."""

    def __init__(self, repo: SqliteRepository, ml: MlServices) -> None:
        self._repo = repo
        self._ml = ml

    def resolve(self, viewer: Viewer, target: SyncTarget) -> Resolved | None:
        if target.kind is SyncKind.FILTER:
            assert target.filters is not None
            f = FiltersIn.model_validate_json(target.filters).to_filter()
            return Resolved(None, filter_ids(self._repo, self._ml, viewer, f))
        assert target.ref_id is not None
        if target.kind is SyncKind.ALBUM:
            album = self._repo.album_info(viewer, target.ref_id)
            if album is None:
                return None
            views = self._repo.album_views(viewer, target.ref_id)
            return Resolved(album.title, [v.id for v in views])
        try:
            person = self._ml.people.get(target.ref_id, viewer)
        except PersonNotFoundError:
            return None
        return Resolved(person.name, self._ml.people.assets(target.ref_id, viewer))
