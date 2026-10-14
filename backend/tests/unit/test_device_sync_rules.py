"""Pure rules of "Keep on my phone" (FEATURES 10.6): what one device's list is made of."""

import pytest

from photo_assistant.domain.device_sync import (
    MAX_PAGE,
    InvalidSyncRuleError,
    SyncKind,
    SyncTarget,
    kept_ids,
    manifest_page,
)


def test_the_list_is_every_include_together_without_any_photo_twice() -> None:
    assert kept_ids([[3, 1, 2], [2, 4]], []) == [1, 2, 3, 4]


def test_an_exclude_takes_its_photos_out_whichever_include_named_them() -> None:
    assert kept_ids([[1, 2, 3], [3, 4]], [[3], [9]]) == [1, 2, 4]


def test_excludes_alone_keep_nothing() -> None:
    assert kept_ids([], [[1, 2]]) == []


def test_no_rules_keep_nothing() -> None:
    assert kept_ids([], []) == []


@pytest.mark.parametrize(
    ("target", "problem"),
    [
        (SyncTarget(SyncKind.ALBUM), "an album rule needs the album"),
        (SyncTarget(SyncKind.PERSON), "a person rule needs the person"),
        (SyncTarget(SyncKind.FILTER), "a filter rule needs the filters"),
        (SyncTarget(SyncKind.ALBUM, ref_id=1, filters="{}"), "an album rule names only the album"),
        (SyncTarget(SyncKind.FILTER, ref_id=1, filters="{}"), "a filter rule names no album"),
    ],
)
def test_a_target_names_exactly_one_thing(target: SyncTarget, problem: str) -> None:
    with pytest.raises(InvalidSyncRuleError, match=problem):
        target.check()


def test_well_formed_targets_pass() -> None:
    SyncTarget(SyncKind.ALBUM, ref_id=4).check()
    SyncTarget(SyncKind.PERSON, ref_id=4).check()
    SyncTarget(SyncKind.FILTER, filters='{"q": "tag:screenshot"}').check()


def test_a_page_starts_after_the_last_id_seen_and_says_where_to_go_on() -> None:
    ids = [2, 5, 7, 9, 11]
    assert manifest_page(ids, after=None, limit=2) == ([2, 5], 5)
    assert manifest_page(ids, after=5, limit=2) == ([7, 9], 9)
    assert manifest_page(ids, after=9, limit=2) == ([11], None)
    assert manifest_page(ids, after=11, limit=2) == ([], None)


def test_the_last_full_page_has_no_next() -> None:
    assert manifest_page([1, 2], after=None, limit=2) == ([1, 2], None)


def test_an_id_that_left_the_list_still_marks_the_place() -> None:
    assert manifest_page([2, 9], after=5, limit=10) == ([9], None)


@pytest.mark.parametrize("limit", [0, -1, MAX_PAGE + 1])
def test_page_sizes_stay_sane(limit: int) -> None:
    with pytest.raises(InvalidSyncRuleError, match="1 to"):
        manifest_page([1], after=None, limit=limit)
