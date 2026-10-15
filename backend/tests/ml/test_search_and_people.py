"""Semantic search, similar photos and people use cases — always within the visible set."""

import math

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.api.settings import MlSettings
from photo_assistant.app.people import FaceNotFoundError, People, PersonNotFoundError
from photo_assistant.app.search import (
    NotIndexedError,
    SearchUnavailableError,
    SemanticSearch,
    SimilarPhotos,
)
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.vectors import Vector
from tests.factories import NOW, new_asset
from tests.ml.fakes import FakeClip


def angle(deg: float) -> Vector:
    return (math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0, 0.0)


def library(repo: SqliteRepository, store: SqliteMlStore, degrees: list[float]) -> list[int]:
    ids = []
    for n, deg in enumerate(degrees, start=1):
        asset = repo.add_asset(new_asset(n), NOW)
        store.save_clip(asset, "clip-fake", angle(deg))
        ids.append(asset)
    return ids


# --- semantic search ------------------------------------------------------------------------------


def test_search_ranks_visible_assets_by_similarity(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    a, b, c, hidden = library(repo, store, [40, 10, 80, 0])
    clip = FakeClip()
    clip.texts["kids in the snow"] = angle(0)
    search = SemanticSearch(clip, store)
    hits = search("kids in the snow", candidates={a, b, c}, limit=2)
    assert [h.asset_id for h in hits] == [b, a]
    assert hits[0].score == pytest.approx(math.cos(math.radians(10)), abs=1e-5)
    assert hidden not in [h.asset_id for h in search("kids in the snow", {a, b, c}, 10)]


def test_search_min_score_and_blank_text(repo: SqliteRepository, store: SqliteMlStore) -> None:
    a, b = library(repo, store, [0, 80])
    clip = FakeClip()
    clip.texts["x"] = angle(0)
    search = SemanticSearch(clip, store, min_score=0.5)
    assert [h.asset_id for h in search("x", {a, b}, 10)] == [a]
    assert search("   ", {a, b}, 10) == []


def test_default_cutoff_keeps_hits_on_the_boundary_and_drops_weaker_ones(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    cutoff = MlSettings(_env_file=None).search_cutoff()  # type: ignore[call-arg]
    assert cutoff == 0.08
    degrees = [math.degrees(math.acos(score)) for score in (0.0801, 0.0799, 0.12)]
    above, below, strong = library(repo, store, degrees)
    clip = FakeClip()
    clip.texts["zebra"] = angle(0)
    hits = SemanticSearch(clip, store, min_score=cutoff)("zebra", {above, below, strong}, 10)
    assert [h.asset_id for h in hits] == [strong, above]


def test_search_without_model_says_so(store: SqliteMlStore) -> None:
    with pytest.raises(SearchUnavailableError, match="just models"):
        SemanticSearch(FakeClip(available=False), store)("snow", {1}, 10)


def test_similar_photos_excludes_itself_and_invisible_ones(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    a, b, c, hidden = library(repo, store, [0, 30, 90, 1])
    similar = SimilarPhotos(store, "clip-fake")
    assert [h.asset_id for h in similar(a, {a, b, c}, 5)] == [b, c]
    with pytest.raises(LookupError):
        similar(hidden, {a, b, c}, 5)


def test_similar_photos_of_an_unanalysed_photo(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    asset = repo.add_asset(new_asset(9), NOW)
    with pytest.raises(NotIndexedError):
        SimilarPhotos(store, "clip-fake")(asset, {asset}, 5)


# --- people ---------------------------------------------------------------------------------------


@pytest.fixture
def family(repo: SqliteRepository, store: SqliteMlStore) -> dict[str, int]:
    """Assets a, b (Lea), c (Tom); d is not visible to the viewer and holds another Lea face."""
    ids = {name: repo.add_asset(new_asset(n), NOW) for n, name in enumerate("abcd", start=1)}

    def face(asset: str) -> int:
        (face_id,) = store.replace_faces(
            ids[asset], "f", [Face(BoundingBox(0, 0, 1, 1), 0.9, (), angle(ord(asset)))]
        )
        return face_id

    fa, fb, fc, fd = face("a"), face("b"), face("c"), face("d")
    lea = store.create_person(fa)
    store.assign_face(fb, lea)
    store.assign_face(fd, lea)
    tom = store.create_person(fc)
    return ids | {"lea": lea, "tom": tom, "fa": fa, "fb": fb, "fc": fc, "fd": fd}


def visible(family: dict[str, int]) -> set[int]:
    return {family["a"], family["b"], family["c"]}


def test_list_and_rename_people(store: SqliteMlStore, family: dict[str, int]) -> None:
    people = People(store)
    renamed = people.rename(family["lea"], "  Léa  ", visible(family))
    assert renamed.name == "Léa" and renamed.face_count == 2  # d's face isn't counted
    assert [p.name for p in people.list_all(visible(family))] == ["Léa", None]
    assert people.rename(family["lea"], "   ", visible(family)).name is None
    with pytest.raises(ValueError, match="long"):
        people.rename(family["lea"], "x" * 101, visible(family))


def test_a_hidden_person_is_listed_only_when_asked_for(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    people = People(store)
    assert people.set_hidden(family["tom"], True, visible(family)).hidden
    assert [p.id for p in people.list_all(visible(family))] == [family["lea"]]
    assert [p.id for p in people.list_all(visible(family), hidden=True)] == [family["tom"]]
    assert people.get(family["tom"], visible(family)).hidden, "still opens by its link"
    assert people.assets(family["tom"], visible(family)) == [family["c"]]
    assert not people.set_hidden(family["tom"], False, visible(family)).hidden
    assert len(people.list_all(visible(family))) == 2
    assert people.list_all(visible(family), hidden=True) == []


def test_hiding_keeps_the_name_and_a_merge_keeps_the_target_as_it_was(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    people = People(store)
    people.rename(family["tom"], "Tom", visible(family))
    assert people.set_hidden(family["tom"], True, visible(family)).name == "Tom"
    merged = people.merge(family["lea"], [family["tom"]], visible(family))
    assert not merged.hidden and merged.face_count == 3


def test_a_person_the_viewer_cannot_see_cannot_be_hidden(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    with pytest.raises(PersonNotFoundError):
        People(store).set_hidden(family["tom"], True, {family["a"]})
    assert not People(store).get(family["tom"], visible(family)).hidden


def test_people_the_viewer_cannot_see_are_not_found(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    people = People(store)
    only_a = {family["a"]}
    with pytest.raises(PersonNotFoundError):
        people.get(family["tom"], only_a)
    with pytest.raises(PersonNotFoundError):
        people.rename(family["tom"], "Tom", only_a)
    with pytest.raises(PersonNotFoundError):
        people.assets(family["tom"], only_a)


def test_person_assets_are_limited_to_visible_ones(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    assets = People(store).assets(family["lea"], visible(family))
    assert assets == [family["b"], family["a"]], "newest first; same moment: highest id first"


def test_merge(store: SqliteMlStore, family: dict[str, int]) -> None:
    people = People(store)
    merged = people.merge(family["lea"], [family["tom"]], visible(family))
    assert merged.face_count == 3
    with pytest.raises(PersonNotFoundError):
        people.get(family["tom"], visible(family))
    with pytest.raises(ValueError, match="itself"):
        people.merge(family["lea"], [family["lea"]], visible(family))
    with pytest.raises(PersonNotFoundError):
        people.merge(family["lea"], [999], visible(family))


def test_split_faces_into_a_new_or_existing_person(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    people = People(store)
    new = people.split([family["fb"]], visible(family), name="Lou")
    assert new.name == "Lou" and new.face_count == 1
    moved = people.split([family["fb"]], visible(family), person_id=family["tom"])
    assert moved.id == family["tom"] and moved.face_count == 2
    with pytest.raises(PersonNotFoundError):
        people.get(new.id, visible(family))  # emptied → removed


def test_split_refuses_faces_on_invisible_photos(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    people = People(store)
    with pytest.raises(FaceNotFoundError):
        people.split([family["fd"]], visible(family))
    with pytest.raises(FaceNotFoundError):
        people.split([12345], visible(family))
    with pytest.raises(ValueError, match="face"):
        people.split([], visible(family))
    with pytest.raises(PersonNotFoundError):
        people.split([family["fa"]], {family["a"]}, person_id=family["tom"])


def test_faces_of_a_visible_asset(store: SqliteMlStore, family: dict[str, int]) -> None:
    people = People(store)
    (face,) = people.faces_of_asset(family["a"], visible(family))
    assert face.person_id == family["lea"]
    with pytest.raises(LookupError):
        people.faces_of_asset(family["d"], visible(family))
