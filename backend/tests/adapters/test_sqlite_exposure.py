"""Exposure settings on the photo row: stored at import, filled in later for older photos."""

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.exposure import Exposure
from tests.factories import NOW, new_asset

SHOT = Exposure(f_number=2.8, exposure_time=1 / 250, iso=400, focal_length=35.0)


def test_a_new_photo_keeps_its_exposure(repo: SqliteRepository) -> None:
    asset_id = repo.add_asset(new_asset(1, exposure=SHOT), NOW)
    stored = repo.get_asset(asset_id)
    assert stored is not None and stored.exposure == SHOT


def test_a_photo_stored_without_exposure_reads_back_empty(repo: SqliteRepository) -> None:
    asset_id = repo.add_asset(new_asset(1), NOW)
    stored = repo.get_asset(asset_id)
    assert stored is not None and stored.exposure.is_empty


def test_a_photo_keeps_the_values_it_has_and_none_for_the_rest(repo: SqliteRepository) -> None:
    asset_id = repo.add_asset(new_asset(1, exposure=Exposure(iso=800)), NOW)
    stored = repo.get_asset(asset_id)
    assert stored is not None and stored.exposure == Exposure(iso=800)


def test_photos_without_any_exposure_value_are_listed_by_id_after_a_cursor(
    repo: SqliteRepository,
) -> None:
    bare = [repo.add_asset(new_asset(n), NOW) for n in (1, 2, 3)]
    repo.add_asset(new_asset(4, exposure=SHOT), NOW)
    repo.add_asset(new_asset(5, exposure=Exposure(iso=100)), NOW)
    assert repo.assets_without_exposure(0, 2) == [
        (bare[0], f"originals/2020/01/{1:064x}.jpg"),
        (bare[1], f"originals/2020/01/{2:064x}.jpg"),
    ]
    assert [i for i, _ in repo.assets_without_exposure(bare[1], 10)] == [bare[2]]
    assert repo.assets_without_exposure(bare[2], 10) == []


def test_a_photo_in_the_trash_is_listed_too_it_may_be_restored(repo: SqliteRepository) -> None:
    asset_id = repo.add_asset(new_asset(1), NOW)
    assert repo.trash_superseded(asset_id, NOW)
    assert [i for i, _ in repo.assets_without_exposure(0, 10)] == [asset_id]


def test_set_exposures_fills_the_named_photos_and_no_other(repo: SqliteRepository) -> None:
    first, second, third = (repo.add_asset(new_asset(n), NOW) for n in (1, 2, 3))
    repo.set_exposures([(first, SHOT), (third, Exposure(focal_length=4.25))])
    read = {i: a.exposure for i in (first, second, third) if (a := repo.get_asset(i))}
    assert read == {first: SHOT, second: Exposure(), third: Exposure(focal_length=4.25)}
    assert [i for i, _ in repo.assets_without_exposure(0, 10)] == [second]
