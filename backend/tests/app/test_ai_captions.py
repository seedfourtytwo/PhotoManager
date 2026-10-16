"""The background caption job: a local vision model describes photos that have none yet."""

from pathlib import Path

import pytest

from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.ai_captions import CAPTION_JOB, CaptionPhotos
from photo_assistant.ports.ai import AIUnavailableError, AIUnreachableError, Capability
from tests.factories import NOW, new_asset
from tests.fakes_ai import FakeAI

MODEL = "qwen3.5:4b"


def _photos(repo: SqliteRepository, root: Path, count: int) -> list[int]:
    ids = []
    for n in range(1, count + 1):
        asset_id = repo.add_asset(new_asset(n), NOW)
        file = root / f"originals/2020/01/{n:064x}.jpg"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(f"photo {n}".encode())
        ids.append(asset_id)
    return ids


def _job(repo: SqliteRepository, ai: FakeAI, root: Path, batch: int = 10) -> CaptionPhotos:
    return CaptionPhotos(repo, ai, MODEL, lambda rel: root / rel, batch=batch)


def _queued(repo: SqliteRepository) -> list[object]:
    return [j["payload"] for j in repo.list_jobs() if j["kind"] == CAPTION_JOB]


def test_photos_without_a_caption_get_one(repo: SqliteRepository, tmp_path: Path) -> None:
    first, second = _photos(repo, tmp_path, 2)
    ai = FakeAI(captions=["A red kite.", "Two dogs."])
    assert _job(repo, ai, tmp_path)({}) == 2
    assert repo.captions_of([first, second]) == {first: "A red kite.", second: "Two dogs."}
    assert ai.images == [b"photo 1", b"photo 2"]
    assert _queued(repo) == [], "a short batch was the last one"


def test_a_full_batch_queues_the_next_one_once(repo: SqliteRepository, tmp_path: Path) -> None:
    _photos(repo, tmp_path, 3)
    job = _job(repo, FakeAI(captions=["a", "b", "c"]), tmp_path, batch=2)
    job({})
    repo.enqueue_once(CAPTION_JOB)  # the periodic check, meanwhile
    assert _queued(repo) == [{}]
    assert job({}) == 1
    assert len(repo.captions_of([1, 2, 3])) == 3


def test_a_photo_the_model_cannot_describe_is_skipped_for_good(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    first, second = _photos(repo, tmp_path, 2)
    ai = FakeAI(captions=[AIUnavailableError("not usable twice"), "Two dogs."])
    assert _job(repo, ai, tmp_path)({}) == 1
    assert repo.captions_of([first, second]) == {second: "Two dogs."}
    assert repo.photos_to_caption(MODEL, 10) == []


def test_a_missing_file_is_skipped_for_good(repo: SqliteRepository, tmp_path: Path) -> None:
    (first,) = _photos(repo, tmp_path, 1)
    (tmp_path / f"originals/2020/01/{1:064x}.jpg").unlink()
    assert _job(repo, FakeAI(), tmp_path)({}) == 0
    assert repo.photos_to_caption(MODEL, 10) == []


def test_an_unreachable_server_fails_the_job_so_it_is_tried_again(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    first, second = _photos(repo, tmp_path, 2)
    ai = FakeAI(captions=["A red kite.", AIUnreachableError("did not answer in time")])
    with pytest.raises(AIUnreachableError):
        _job(repo, ai, tmp_path)({})
    assert repo.captions_of([first]) == {first: "A red kite."}, "what was done is kept"
    assert [i for i, _ in repo.photos_to_caption(MODEL, 10)] == [second]


def test_nothing_is_asked_while_the_server_offers_no_captions(
    repo: SqliteRepository, tmp_path: Path
) -> None:
    _photos(repo, tmp_path, 1)
    ai = FakeAI(captions=["never"], capabilities=frozenset({Capability.PLAN_ALBUM}))
    assert _job(repo, ai, tmp_path)({}) == 0
    assert ai.images == []
    assert len(repo.photos_to_caption(MODEL, 10)) == 1, "asked again on the next round"
