"""Held for review: doubtful photos leave the library until a person keeps or discards them."""

from datetime import datetime
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database
from photo_assistant.app.enrich import GroupSimilar
from photo_assistant.app.review import Review
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.tags import TagScore
from photo_assistant.ports import RenderedImage
from tests.factories import NOW, new_asset

ADMIN = Viewer(1, Role.ADMIN)
SAME = "0000000000000000"


class FixedClock:
    def now(self) -> datetime:
        return NOW


class NamedHasher:
    """The thumbnail's file name says what the photo looks like."""

    def phash(self, image: Path) -> str:
        return SAME if "same" in image.name else f"{int(image.stem.split('-')[-1]):02x}" * 8


@pytest.fixture
def repo() -> SqliteRepository:
    repo = SqliteRepository(open_database(":memory:"))
    repo.add_user("c", "C", "hash", Role.ADMIN)
    return repo


@pytest.fixture
def review(repo: SqliteRepository) -> Review:
    return Review(repo, FixedClock())


def photo(repo: SqliteRepository, n: int, look: str = "own", **kw: object) -> int:
    asset_id = repo.add_asset(new_asset(n, **kw), NOW)
    repo.set_thumbnail(asset_id, RenderedImage(f"derived/thumb/{look}-{n}.webp", 1, 1))
    return asset_id


def library(repo: SqliteRepository) -> set[int]:
    return {v.id for v in repo.list_all_views(ADMIN, AssetFilter())}


def waiting(review: Review) -> dict[int, tuple[str | None, int | None]]:
    return {v.id: (v.held_reason, v.held_like) for v in review.waiting(ADMIN)}


def grouper(repo: SqliteRepository, review: Review) -> GroupSimilar:
    return GroupSimilar(repo, NamedHasher(), lambda rel: Path(rel), review=review)


def test_a_new_photo_that_looks_like_a_library_photo_waits_for_review(
    repo: SqliteRepository, review: Review
) -> None:
    old = photo(repo, 1, "same", taken_at=datetime(2019, 7, 1, 12, 0, 0))
    grouper(repo, review)({})
    copy = photo(repo, 2, "same", taken_at=datetime(2023, 1, 1, 9, 0, 0))
    fresh = photo(repo, 3)
    grouper(repo, review)({})
    assert library(repo) == {old, fresh}
    assert waiting(review) == {copy: ("lookalike", old)}
    assert repo.count_visible(ADMIN) == 2


def test_look_alikes_within_one_import_are_a_burst_not_a_review(
    repo: SqliteRepository, review: Review
) -> None:
    a = photo(repo, 1, "same", taken_at=datetime(2019, 7, 1, 12, 0, 0))
    b = photo(repo, 2, "same", taken_at=datetime(2019, 7, 1, 12, 0, 1))
    grouper(repo, review)({})
    assert library(repo) == {a, b} and waiting(review) == {}
    assert {v.group_id for v in repo.list_all_views(ADMIN, AssetFilter())} == {a}


def test_two_frames_of_a_burst_hashed_by_two_jobs_are_grouped_not_held(
    repo: SqliteRepository, review: Review
) -> None:
    """Phone uploads queue one scan per request, so a burst's frames are hashed job by job."""
    a = photo(repo, 1, "same", taken_at=datetime(2019, 7, 1, 12, 0, 0))
    grouper(repo, review)({})
    b = photo(repo, 2, "same", taken_at=datetime(2019, 7, 1, 12, 0, 1))
    grouper(repo, review)({})
    c = photo(repo, 3, "same", taken_at=datetime(2019, 7, 1, 12, 10, 0))
    grouper(repo, review)({})
    assert library(repo) == {a, b, c} and waiting(review) == {}
    assert {v.group_id for v in repo.list_all_views(ADMIN, AssetFilter())} == {a}


def test_a_frame_of_a_new_burst_that_copies_an_old_photo_is_still_held_like_the_old_one(
    repo: SqliteRepository, review: Review
) -> None:
    old = photo(repo, 1, "same", taken_at=datetime(2019, 7, 1, 12, 0, 0))
    first = photo(repo, 2, "own", taken_at=datetime(2023, 1, 1, 9, 0, 0))
    grouper(repo, review)({})
    second = photo(repo, 3, "same", taken_at=datetime(2023, 1, 1, 9, 0, 1))
    grouper(repo, review)({})
    assert library(repo) == {old, first}
    assert waiting(review) == {second: ("lookalike", old)}


def test_a_held_photo_does_not_join_groups_until_it_is_kept(
    repo: SqliteRepository, review: Review
) -> None:
    old = photo(repo, 1, "same", taken_at=datetime(2019, 7, 1, 12, 0, 0))
    copy = photo(repo, 2, "same", taken_at=datetime(2019, 7, 1, 12, 0, 1))
    assert review.hold_clutter(copy, [TagScore("screenshot", 0.08)]) is True
    grouper(repo, review)({})
    assert [v.group_id for v in repo.list_all_views(ADMIN, AssetFilter())] == [None]
    assert review.keep([copy]) == 1
    grouper(repo, review)({"full": True})
    assert library(repo) == {old, copy} and waiting(review) == {}
    assert {v.group_id for v in repo.list_all_views(ADMIN, AssetFilter())} == {old}


def test_clutter_waits_for_review_under_its_own_name(
    repo: SqliteRepository, review: Review
) -> None:
    shot, meal = photo(repo, 1), photo(repo, 2)
    assert review.hold_clutter(shot, [TagScore("screenshot", 0.08)]) is True
    assert review.hold_clutter(meal, [TagScore("food", 0.08), TagScore("receipt", 0.04)]) is False
    assert library(repo) == {meal}
    assert waiting(review) == {shot: ("screenshot", None)}


def test_a_kept_photo_joins_the_library_and_is_never_held_again(
    repo: SqliteRepository, review: Review
) -> None:
    shot = photo(repo, 1)
    review.hold_clutter(shot, [TagScore("document", 0.08)])
    assert review.keep([shot]) == 1
    assert library(repo) == {shot} and waiting(review) == {}
    assert review.hold_clutter(shot, [TagScore("document", 0.08)]) is False
    assert review.hold_lookalikes({shot}) == 0
    assert library(repo) == {shot}
    assert review.keep([shot]) == 0, "nothing left to keep"


def test_a_discarded_photo_goes_to_the_trash_and_a_restore_puts_it_in_the_library(
    repo: SqliteRepository, review: Review
) -> None:
    shot, other = photo(repo, 1), photo(repo, 2)
    review.hold_clutter(shot, [TagScore("meme", 0.08)])
    assert review.discard([shot, other], user_id=1) == 1, "only held photos are discarded here"
    assert waiting(review) == {} and library(repo) == {other}
    assert [v.id for v in repo.trashed_views(ADMIN)] == [shot]
    repo.restore_assets([shot])
    assert library(repo) == {shot, other} and waiting(review) == {}


def test_a_photo_in_the_trash_or_already_waiting_is_left_alone(
    repo: SqliteRepository, review: Review
) -> None:
    gone, held = photo(repo, 1), photo(repo, 2)
    repo.trash_assets([gone], 1, NOW)
    review.hold_clutter(held, [TagScore("receipt", 0.08)])
    assert review.hold_clutter(gone, [TagScore("receipt", 0.08)]) is False
    assert review.hold_clutter(held, [TagScore("meme", 0.08)]) is False
    assert waiting(review) == {held: ("receipt", None)}


def test_held_and_trashed_photos_are_not_what_new_photos_are_compared_with(
    repo: SqliteRepository, review: Review
) -> None:
    held, gone = photo(repo, 1, "same"), photo(repo, 2, "same")
    grouper(repo, review)({})
    review.hold_clutter(held, [TagScore("document", 0.08)])
    repo.trash_assets([gone], 1, NOW)
    new = photo(repo, 3, "same")
    grouper(repo, review)({})
    assert library(repo) == {new}


def test_people_only_review_what_they_may_see(repo: SqliteRepository, review: Review) -> None:
    shot = photo(repo, 1)
    review.hold_clutter(shot, [TagScore("document", 0.08)])
    stranger = repo.add_user("lea", "Lea", "hash", Role.MEMBER)
    assert review.waiting(Viewer(stranger.id, Role.MEMBER)) == []
    assert review.count(ADMIN) == 1 and review.count(Viewer(stranger.id, Role.MEMBER)) == 0
