"""A person's portrait (issue 53): the store keeps the chosen circle, the use case checks who
may choose what and renders the round picture once per photo and cut."""

from pathlib import Path

import pytest

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.people import FaceNotFoundError, People, PersonNotFoundError
from photo_assistant.app.portraits import PORTRAIT_EDGE, Portraits, portrait_version
from photo_assistant.domain.faces import (
    BoundingBox,
    Circle,
    Face,
    InvalidPortraitError,
    automatic_circle,
)
from photo_assistant.domain.library_paths import portrait_relpath
from photo_assistant.ports import RenderSpec
from tests.factories import NOW, new_asset
from tests.ml.fakes import FakeLibrary

M = "f"
BOX = BoundingBox(0.4, 0.3, 0.1, 0.2)
CHOSEN = Circle(0.5, 0.5, 0.4)


def face(score: float = 0.9, box: BoundingBox = BOX) -> Face:
    return Face(box, score, (), (1.0, 0.0, 0.0))


@pytest.fixture
def family(repo: SqliteRepository, store: SqliteMlStore) -> dict[str, int]:
    """Lea: faces on a (the first found), b (the sharpest) and d, which the viewer does not
    see. Tom: one face on c."""
    ids = {name: repo.add_asset(new_asset(n), NOW) for n, name in enumerate("abcd", start=1)}
    scores = {"a": 0.8, "b": 0.95, "c": 0.9, "d": 0.99}
    faces = {
        f"f{name}": store.replace_faces(ids[name], M, [face(scores[name])])[0] for name in "abcd"
    }
    lea = store.create_person(faces["fa"])
    store.assign_face(faces["fb"], lea)
    store.assign_face(faces["fd"], lea)
    tom = store.create_person(faces["fc"])
    return ids | faces | {"lea": lea, "tom": tom}


def visible(family: dict[str, int]) -> set[int]:
    return {family["a"], family["b"], family["c"]}


def everything(family: dict[str, int]) -> set[int]:
    return visible(family) | {family["d"]}


# --- the store --------------------------------------------------------------------------------


def test_without_a_choice_the_portrait_is_the_automatic_circle_of_the_cover(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None and lea.cover_face is not None
    assert lea.portrait.face == lea.cover_face and lea.cover_face.id == family["fa"]
    assert lea.portrait.chosen is False
    assert lea.portrait.photo_size == (4000, 3000)
    assert lea.portrait.circle == automatic_circle(BOX, 4000, 3000)
    assert lea.portrait.content_hash == new_asset(1).content_hash
    assert lea.portrait.library_path == new_asset(1).library_path


def test_a_chosen_portrait_is_that_face_and_that_circle(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    store.set_portrait(family["lea"], family["fb"], CHOSEN)
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None and lea.cover_face is not None
    assert (lea.cover_face.id, lea.portrait.face.id) == (family["fb"], family["fb"])
    assert (lea.portrait.chosen, lea.portrait.circle) == (True, CHOSEN)
    (listed,) = (p for p in store.list_persons(visible(family)) if p.id == family["lea"])
    assert listed == lea
    tom = store.get_person(family["tom"], visible(family))
    assert tom is not None and tom.portrait is not None and not tom.portrait.chosen


def test_clearing_keeps_the_photo_and_goes_back_to_the_automatic_circle(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    store.set_portrait(family["lea"], family["fb"], CHOSEN)
    store.clear_portrait(family["lea"])
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None
    assert (lea.portrait.face.id, lea.portrait.chosen) == (family["fb"], False)
    assert lea.portrait.circle == automatic_circle(BOX, 4000, 3000)


def test_a_viewer_who_may_not_see_the_chosen_photo_gets_an_automatic_one_they_may_see(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    store.set_portrait(family["lea"], family["fd"], CHOSEN)
    allowed = store.get_person(family["lea"], everything(family))
    assert allowed is not None and allowed.portrait is not None
    assert (allowed.portrait.face.id, allowed.portrait.chosen) == (family["fd"], True)
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None
    assert lea.portrait.face.id == family["fb"], "the best face on a photo they may see"
    assert lea.portrait.chosen is False
    assert lea.portrait.circle == automatic_circle(BOX, 4000, 3000), "never the hidden cut"


def test_the_portrait_is_automatic_again_when_its_face_goes_to_someone_else(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    store.set_portrait(family["lea"], family["fb"], CHOSEN)
    store.move_faces([family["fb"]], family["tom"])
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None
    assert (lea.portrait.face.id, lea.portrait.chosen) == (family["fa"], False)
    tom = store.get_person(family["tom"], visible(family))
    assert tom is not None and tom.portrait is not None and not tom.portrait.chosen


def test_the_portrait_is_automatic_again_when_its_photo_is_gone(
    db: Database, store: SqliteMlStore, family: dict[str, int]
) -> None:
    store.set_portrait(family["lea"], family["fb"], CHOSEN)
    with db.transaction() as conn:
        conn.execute("DELETE FROM asset WHERE id = ?", (family["b"],))
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None
    assert (lea.portrait.face.id, lea.portrait.chosen) == (family["fa"], False)


def test_a_chosen_portrait_survives_the_photo_being_analysed_again(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    """Detection replaces a photo's faces: the one found where the cover was takes its place,
    and is the portrait again as soon as it is placed with the same person."""
    store.set_portrait(family["lea"], family["fb"], CHOSEN)
    nearly = BoundingBox(BOX.x + 0.005, BOX.y, BOX.width, BOX.height)
    elsewhere = BoundingBox(0.7, 0.7, 0.1, 0.2)
    other, again = store.replace_faces(family["b"], M, [face(0.99, elsewhere), face(0.9, nearly)])
    waiting = store.get_person(family["lea"], visible(family))
    assert waiting is not None and waiting.portrait is not None
    assert waiting.portrait.chosen is False, "the new face is nobody's yet"
    store.assign_face(again, family["lea"])
    store.assign_face(other, family["lea"])
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None
    assert (lea.portrait.face.id, lea.portrait.chosen) == (again, True)
    assert lea.portrait.circle == CHOSEN


def test_a_cover_whose_face_is_not_found_again_is_let_go(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    store.set_portrait(family["lea"], family["fb"], CHOSEN)
    (moved,) = store.replace_faces(family["b"], M, [face(0.9, BoundingBox(0.7, 0.7, 0.1, 0.2))])
    store.assign_face(moved, family["lea"])
    lea = store.get_person(family["lea"], visible(family))
    assert lea is not None and lea.portrait is not None and lea.portrait.chosen is False


def test_a_photo_without_a_known_size_uses_its_thumbnail_shape_then_a_square(
    repo: SqliteRepository, store: SqliteMlStore
) -> None:
    from photo_assistant.ports import RenderedImage

    unknown = repo.add_asset(new_asset(7, width=None, height=None), NOW)
    (face_id,) = store.replace_faces(unknown, M, [face()])
    person = store.create_person(face_id)
    found = store.get_person(person, {unknown})
    assert found is not None and found.portrait is not None
    assert found.portrait.photo_size == (1, 1)
    repo.set_thumbnail(unknown, RenderedImage("derived/thumb/00/x.webp", 640, 480))
    found = store.get_person(person, {unknown})
    assert found is not None and found.portrait is not None
    assert found.portrait.photo_size == (640, 480)


def test_a_persons_faces_come_best_first_on_photos_the_viewer_may_see(
    store: SqliteMlStore, family: dict[str, int]
) -> None:
    faces = store.person_faces(family["lea"], visible(family), limit=10)
    assert [p.face.id for p in faces] == [family["fb"], family["fa"]]
    assert all(not p.chosen and p.circle == automatic_circle(BOX, 4000, 3000) for p in faces)
    assert [p.face.id for p in store.person_faces(family["lea"], visible(family), limit=1)] == [
        family["fb"]
    ]
    everyone = store.person_faces(family["lea"], everything(family), limit=10)
    assert [p.face.id for p in everyone] == [family["fd"], family["fb"], family["fa"]]
    (twin,) = store.replace_faces(family["c"], "g", [face(0.95)])  # same score as b: id decides
    store.assign_face(twin, family["lea"])
    tied = store.person_faces(family["lea"], visible(family), limit=2)
    assert [p.face.id for p in tied] == [family["fb"], twin]


def test_the_portrait_of_one_face(store: SqliteMlStore, family: dict[str, int]) -> None:
    found = store.face_portrait(family["fc"])
    assert found is not None and found.face.id == family["fc"] and not found.chosen
    assert found.circle == automatic_circle(BOX, 4000, 3000)
    assert store.face_portrait(9999) is None


# --- the use case -----------------------------------------------------------------------------


class WritingRenderer:
    """Writes a marker where the picture would go and remembers what was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[Path, RenderSpec]] = []

    def render_variant(self, source: Path, destination: Path, spec: RenderSpec) -> tuple[int, int]:
        self.asked.append((source, spec))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"portrait")
        return PORTRAIT_EDGE, PORTRAIT_EDGE


@pytest.fixture
def library(tmp_path: Path, family: dict[str, int]) -> FakeLibrary:
    found = FakeLibrary(tmp_path / "data")
    for n in (1, 2, 3, 4):
        original = found.absolute(new_asset(n).library_path)
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"original")
    return found


@pytest.fixture
def renderer() -> WritingRenderer:
    return WritingRenderer()


@pytest.fixture
def portraits(store: SqliteMlStore, library: FakeLibrary, renderer: WritingRenderer) -> Portraits:
    return Portraits(store, People(store), library, renderer)  # type: ignore[arg-type]


def test_choosing_a_portrait_keeps_the_face_and_the_circle(
    portraits: Portraits, family: dict[str, int]
) -> None:
    lea = portraits.choose(family["lea"], family["fb"], CHOSEN, visible(family))
    assert lea.portrait is not None
    assert (lea.portrait.face.id, lea.portrait.chosen, lea.portrait.circle) == (
        family["fb"],
        True,
        CHOSEN,
    )


def test_what_a_client_sends_is_brought_inside_the_photo(
    portraits: Portraits, family: dict[str, int]
) -> None:
    lea = portraits.choose(family["lea"], family["fb"], Circle(9, -9, 9), visible(family))
    assert lea.portrait is not None
    circle = lea.portrait.circle
    assert (circle.cx, circle.cy, circle.size) == pytest.approx((0.625, 0.5, 1.0))
    with pytest.raises(InvalidPortraitError):
        portraits.choose(family["lea"], family["fb"], Circle(float("nan"), 0, 1), visible(family))


def test_only_a_face_of_that_person_on_a_photo_the_viewer_sees_can_be_chosen(
    store: SqliteMlStore, portraits: Portraits, family: dict[str, int]
) -> None:
    for face_id in (family["fc"], family["fd"], 9999):  # Tom's, on a hidden photo, no such face
        with pytest.raises(FaceNotFoundError, match=f"no face {face_id}"):
            portraits.choose(family["lea"], face_id, CHOSEN, visible(family))
    with pytest.raises(PersonNotFoundError):
        portraits.choose(9999, family["fa"], CHOSEN, visible(family))
    with pytest.raises(PersonNotFoundError):
        portraits.choose(family["tom"], family["fc"], CHOSEN, {family["a"]})
    lea = store.get_person(family["lea"], everything(family))
    assert lea is not None and lea.portrait is not None and not lea.portrait.chosen, "untouched"


def test_use_automatic_clears_the_choice(portraits: Portraits, family: dict[str, int]) -> None:
    portraits.choose(family["lea"], family["fb"], CHOSEN, visible(family))
    lea = portraits.use_automatic(family["lea"], visible(family))
    assert lea.portrait is not None and not lea.portrait.chosen
    with pytest.raises(PersonNotFoundError):
        portraits.use_automatic(9999, visible(family))


def test_candidates_are_the_persons_faces_the_viewer_may_see(
    portraits: Portraits, family: dict[str, int]
) -> None:
    found = portraits.candidates(family["lea"], visible(family), limit=5)
    assert [p.face.id for p in found] == [family["fb"], family["fa"]]
    with pytest.raises(PersonNotFoundError):
        portraits.candidates(family["tom"], {family["a"]}, limit=5)


def test_the_picture_is_cut_from_the_original_once_and_kept_under_derived(
    portraits: Portraits, library: FakeLibrary, renderer: WritingRenderer, family: dict[str, int]
) -> None:
    portrait = portraits.of_person(family["lea"], visible(family))
    path = portraits.image(portrait)
    assert path.read_bytes() == b"portrait"
    ((source, spec),) = renderer.asked
    assert source == library.absolute(new_asset(1).library_path)
    assert spec.max_edge == PORTRAIT_EDGE == 320 and spec.format == "webp"
    assert spec.recipe is not None and (crop := spec.recipe.crop) is not None
    assert (crop.w * 4000, crop.h * 3000) == pytest.approx((1200, 1200)), "pixel-square"
    relative = portrait_relpath(new_asset(1).content_hash, spec.recipe.key)
    assert path == library.absolute(str(relative))
    assert portraits.image(portrait) == path and len(renderer.asked) == 1, "made once"
    assert source.read_bytes() == b"original"


def test_the_version_changes_with_the_photo_and_with_the_cut(
    portraits: Portraits, family: dict[str, int]
) -> None:
    before = portraits.of_person(family["lea"], visible(family))
    portraits.choose(family["lea"], family["fa"], CHOSEN, visible(family))
    cut = portraits.of_person(family["lea"], visible(family))
    portraits.choose(family["lea"], family["fb"], CHOSEN, visible(family))
    other_photo = portraits.of_person(family["lea"], visible(family))
    versions = {portrait_version(p) for p in (before, cut, other_photo)}
    assert len(versions) == 3
    assert portrait_version(before) == portrait_version(
        portraits.of_face(family["fa"], visible(family))
    ), "the same picture has the same version, whoever asks"


def test_a_new_choice_removes_the_picture_of_the_one_before(
    portraits: Portraits, library: FakeLibrary, family: dict[str, int]
) -> None:
    def kept() -> list[str]:
        return sorted(p.name for p in library.absolute("derived/portrait").rglob("*.webp"))

    portraits.choose(family["lea"], family["fb"], CHOSEN, visible(family))
    first = portraits.image(portraits.of_person(family["lea"], visible(family)))
    automatic = portraits.image(portraits.of_face(family["fb"], visible(family)))
    assert kept() == sorted([first.name, automatic.name])
    portraits.choose(family["lea"], family["fb"], Circle(0.5, 0.5, 0.6), visible(family))
    assert kept() == [automatic.name], "a face's automatic picture is still a candidate"
    second = portraits.image(portraits.of_person(family["lea"], visible(family)))
    portraits.use_automatic(family["lea"], visible(family))
    assert not second.exists() and automatic.exists()


def test_faces_and_people_the_viewer_cannot_see_have_no_picture(
    portraits: Portraits, family: dict[str, int]
) -> None:
    with pytest.raises(FaceNotFoundError):
        portraits.of_face(family["fd"], visible(family))
    with pytest.raises(FaceNotFoundError):
        portraits.of_face(9999, visible(family))
    with pytest.raises(PersonNotFoundError):
        portraits.of_person(family["tom"], {family["a"]})


def test_a_missing_original_is_not_found_and_nothing_is_written(
    portraits: Portraits, library: FakeLibrary, renderer: WritingRenderer, family: dict[str, int]
) -> None:
    from photo_assistant.app.portraits import PortraitUnavailableError

    library.absolute(new_asset(1).library_path).unlink()
    with pytest.raises(PortraitUnavailableError, match="original"):
        portraits.image(portraits.of_person(family["lea"], visible(family)))
    assert renderer.asked == []
