"""What the local AI made: photo captions and suggested-album plans (migration 0035)."""

from datetime import datetime

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.domain.album_plan import AlbumPlan, PlanSection
from photo_assistant.domain.media_types import MediaKind
from tests.factories import NOW, new_asset

MODEL = "qwen3.5:4b"
PLAN = AlbumPlan("Beach day", (PlanSection("Morning", (1, 2), "two-side", {1: "Waves"}),))


def test_photos_to_caption_are_live_photos_without_one_newest_first(
    repo: SqliteRepository,
) -> None:
    first, second, third = (
        repo.add_asset(new_asset(n, datetime(2020, 1, 4 - n)), NOW) for n in (1, 2, 3)
    )
    repo.add_asset(new_asset(4, kind=MediaKind.VIDEO, mime_type="video/mp4"), NOW)
    trashed = repo.add_asset(new_asset(5), NOW)
    assert repo.trash_superseded(trashed, NOW)
    repo.save_caption(second, "Two dogs.", MODEL, "en")

    assert repo.photos_to_caption(MODEL, 10) == [
        (first, f"originals/2020/01/{1:064x}.jpg"),
        (third, f"originals/2020/01/{3:064x}.jpg"),
    ]
    assert len(repo.photos_to_caption(MODEL, 1)) == 1
    assert [i for i, _ in repo.photos_to_caption(MODEL, 10, among=[third, second])] == [third]


def test_the_preview_is_read_rather_than_the_original(repo: SqliteRepository) -> None:
    asset_id = repo.add_asset(new_asset(1), NOW)
    repo._write("UPDATE asset SET preview_path = 'previews/1.jpg' WHERE id = ?", (asset_id,))
    assert repo.photos_to_caption(MODEL, 10) == [(asset_id, "previews/1.jpg")]


def test_a_photo_the_model_could_not_describe_is_not_asked_again_by_that_model(
    repo: SqliteRepository,
) -> None:
    asset_id = repo.add_asset(new_asset(1), NOW)
    repo.caption_failed(asset_id, MODEL, "the answer was not usable twice")
    assert repo.photos_to_caption(MODEL, 10) == []
    assert [i for i, _ in repo.photos_to_caption("other:7b", 10)] == [asset_id]


def test_captions_and_tags_are_read_for_the_named_photos(repo: SqliteRepository) -> None:
    first, second, third = (repo.add_asset(new_asset(n), NOW) for n in (1, 2, 3))
    repo.save_caption(first, "Old text.", MODEL, "en")
    repo.save_caption(first, "A red kite.", MODEL, "en")
    repo.save_caption(third, "Not asked for.", MODEL, "en")
    beach = repo._write("INSERT INTO tag (name) VALUES ('beach')")
    sea = repo._write("INSERT INTO tag (name) VALUES ('sea')")
    for asset_id, tag in ((first, beach), (first, sea), (second, sea), (third, sea)):
        repo._write(
            "INSERT INTO asset_tag (asset_id, tag_id, by) VALUES (?, ?, 'model')", (asset_id, tag)
        )

    assert repo.captions_of([first, second]) == {first: "A red kite."}
    assert repo.tags_of_assets([first, second]) == {first: ("beach", "sea"), second: ("sea",)}
    assert repo.captions_of([]) == {}


def test_a_plan_is_found_only_for_the_photos_it_was_made_for(repo: SqliteRepository) -> None:
    repo.save_album_plan("event-1", "1,2", MODEL, PLAN)
    assert repo.album_plan("event-1", "1,2") == PLAN
    assert repo.album_plan("event-1", "1,2,3") is None
    assert repo.album_plan("event-2", "1,2") is None


def test_a_new_plan_for_an_event_replaces_its_older_ones(repo: SqliteRepository) -> None:
    newer = AlbumPlan("Beach week", PLAN.sections)
    repo.save_album_plan("event-1", "1,2", MODEL, PLAN)
    repo.save_album_plan("event-1", "1", MODEL, PLAN)
    repo.save_album_plan("event-2", "5", MODEL, PLAN)
    repo.save_album_plan("event-1", "1,2", MODEL, newer)

    rows = repo._all("SELECT key, photos FROM album_suggestion_plan ORDER BY key")
    assert [tuple(r) for r in rows] == [("event-1", "1,2"), ("event-2", "5")]
    assert repo.album_plan("event-1", "1,2") == newer
