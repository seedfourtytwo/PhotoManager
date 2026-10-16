"""AI plans for suggested albums: the local model names and arranges one event's photos in the
background; the suggestion shows its title once there is one, the plain title until then."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app import album_suggestions
from photo_assistant.app.ai_captions import CaptionPhotos
from photo_assistant.app.album_plans import MAX_PLAN_PHOTOS, PLAN_JOB, AlbumPlanner, photos_key
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.album_plan import AlbumPlan, PlanSection
from photo_assistant.domain.places import Place
from photo_assistant.ports.ai import AIUnavailableError, AIUnreachableError, Capability
from tests.factories import NOW, new_asset
from tests.fakes_ai import FakeAI

MODEL = "qwen3.5:4b"
JULY = datetime(2025, 7, 12, 10)
PLAIN = "Saint-Malo · 12 July 2025"


@pytest.fixture
def viewer(repo: SqliteRepository) -> Viewer:
    return Viewer.of(repo.add_user("lea", "Lea", "h", Role.ADMIN))


def _event(repo: SqliteRepository, count: int = 8) -> list[int]:
    """One day out in Saint-Malo, an hour between photos."""
    family = repo.add_source("Family", "/family").id
    ids = []
    for n in range(1, count + 1):
        at = JULY + timedelta(minutes=10 * n)
        asset_id = repo.add_asset(new_asset(n, at, latitude=48.65, longitude=-2.03), NOW)
        repo.add_asset_source(asset_id, family, f"{n}.jpg")
        ids.append(asset_id)
    repo.set_places([(i, Place("France", "Brittany", "Saint-Malo")) for i in ids])
    return ids


def _plan(ids: list[int], title: str = "Kites on the beach") -> AlbumPlan:
    return AlbumPlan(title, (PlanSection("The beach", tuple(ids), "single", {ids[0]: "Wind"}),))


def _planner(repo: SqliteRepository, ai: FakeAI, model: str | None = MODEL) -> AlbumPlanner:
    return AlbumPlanner(repo, ai, model)


def _jobs(repo: SqliteRepository) -> list[object]:
    return [j["payload"] for j in repo.list_jobs() if j["kind"] == PLAN_JOB]


def test_until_a_plan_is_made_the_title_is_plain_and_a_plan_is_queued_once(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    planner = _planner(repo, FakeAI())
    (shown,) = planner.suggestions(viewer)
    assert shown.title == PLAIN
    planner.suggestions(viewer)
    assert _jobs(repo) == [{"user_id": viewer.user_id, "key": str(ids[0])}]


def test_the_job_plans_the_event_and_the_suggestion_takes_its_title(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    repo.save_caption(ids[0], "A red kite | over the sea.", MODEL, "en")
    ai = FakeAI(plans=[_plan(ids)])
    planner = _planner(repo, ai)

    assert planner({"user_id": viewer.user_id, "key": str(ids[0])}) is True

    (prompt, context) = ai.planned[0]
    assert PLAIN in prompt, "the plain title is a hint"
    assert [a.id for a in context.assets] == ids, "only this event's photos, all of them"
    assert context.assets[0].place == "Saint-Malo, Brittany, France"
    assert context.assets[0].caption == "A red kite | over the sea."
    assert context.layouts["four-grid"] == 4 and "text" not in context.layouts
    assert repo.album_plan(str(ids[0]), photos_key(ids)) == _plan(ids)
    (shown,) = planner.suggestions(viewer)
    assert shown.title == "Kites on the beach"
    assert _jobs(repo) == []


def test_keep_names_the_album_with_the_plan_title(repo: SqliteRepository, viewer: Viewer) -> None:
    ids = _event(repo)
    planner = _planner(repo, FakeAI(plans=[_plan(ids)]))
    planner({"user_id": viewer.user_id, "key": str(ids[0])})
    album_id = album_suggestions.keep(repo, viewer, str(ids[0]), NOW, planner.namer)
    album = repo.album_info(viewer, album_id)
    assert album is not None and album.title == "Kites on the beach"


def test_photos_without_a_caption_are_described_before_planning(
    repo: SqliteRepository, viewer: Viewer, tmp_path: Path
) -> None:
    ids = _event(repo, 8)
    repo.save_caption(ids[0], "Already seen.", MODEL, "en")
    for n in range(1, 9):
        file = tmp_path / f"originals/2020/01/{n:064x}.jpg"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"jpeg")
    ai = FakeAI(captions=[f"Photo {n}." for n in range(2, 9)], plans=[_plan(ids)])
    captions = CaptionPhotos(repo, ai, MODEL, lambda rel: tmp_path / rel)
    planner = AlbumPlanner(repo, ai, MODEL, captions)

    planner({"user_id": viewer.user_id, "key": str(ids[0])})

    assert len(ai.images) == 7
    described = [a.caption for a in ai.planned[0][1].assets]
    assert described[0] == "Already seen." and all(described)


def test_a_plan_is_only_used_for_the_photos_it_was_made_for(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    repo.save_album_plan(str(ids[0]), photos_key(ids[:-1]), MODEL, _plan(ids[:-1]))
    (shown,) = _planner(repo, FakeAI()).suggestions(viewer)
    assert shown.title == PLAIN, "the event grew (or this viewer sees other photos)"


def test_with_the_ai_off_the_title_stays_plain_and_nothing_is_queued(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    repo.save_album_plan(str(ids[0]), photos_key(ids), MODEL, _plan(ids))
    (shown,) = _planner(repo, FakeAI(), model=None).suggestions(viewer)
    assert shown.title == PLAIN
    assert _jobs(repo) == []


def test_a_failed_plan_keeps_the_plain_title_and_is_not_queued_again(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    planner = _planner(repo, FakeAI(plans=[AIUnavailableError("not usable twice")]))
    assert planner({"user_id": viewer.user_id, "key": str(ids[0])}) is False
    (shown,) = planner.suggestions(viewer)
    assert shown.title == PLAIN
    assert _jobs(repo) == []


def test_an_unreachable_server_fails_the_job_so_it_is_tried_again(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    planner = _planner(repo, FakeAI(plans=[AIUnreachableError("did not answer in time")]))
    with pytest.raises(AIUnreachableError):
        planner({"user_id": viewer.user_id, "key": str(ids[0])})
    assert repo.album_plan(str(ids[0]), photos_key(ids)) is None


def test_nothing_is_asked_while_the_server_offers_no_planning(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo)
    ai = FakeAI(plans=[_plan(ids)], capabilities=frozenset({Capability.CAPTION}))
    assert _planner(repo, ai)({"user_id": viewer.user_id, "key": str(ids[0])}) is False
    assert ai.planned == []


def test_events_too_big_for_the_model_keep_the_plain_title(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ids = _event(repo, MAX_PLAN_PHOTOS + 1)
    ai = FakeAI(plans=[_plan(ids)])
    planner = _planner(repo, ai)
    planner.suggestions(viewer)
    assert _jobs(repo) == []
    assert planner({"user_id": viewer.user_id, "key": str(ids[0])}) is False
    assert ai.planned == []


def test_a_job_for_an_event_that_is_gone_does_nothing(
    repo: SqliteRepository, viewer: Viewer
) -> None:
    ai = FakeAI()
    assert _planner(repo, ai)({"user_id": viewer.user_id, "key": "999"}) is False
    assert _planner(repo, ai)({"user_id": 999, "key": "1"}) is False
