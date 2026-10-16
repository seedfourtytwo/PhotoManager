"""Suggested albums (FEATURES 5.6): events proposed as albums for the signed-in account, made
only when it keeps one, never shown again once it answered."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import IntegrationSettings
from photo_assistant.app.album_plans import PLAN_JOB, photos_key
from photo_assistant.domain.access import SourceAccess
from photo_assistant.domain.album_plan import AlbumPlan, PlanSection
from photo_assistant.domain.places import Place
from tests.api.conftest import BASE, PIN, add_user, make_settings, refusal, services_of
from tests.factories import NOW, new_asset

MALO = {"latitude": 48.65, "longitude": -2.03}
RENNES = {"latitude": 48.11, "longitude": -1.68}


@pytest.fixture
def library(admin: TestClient) -> dict[str, list[int]]:
    return _library(admin)


def _library(admin: TestClient) -> dict[str, list[int]]:
    """A life at home in Rennes, a trip to Saint-Malo in July 2025 (one photo of it in a folder
    only admins see) and a birthday at home in March 2025."""
    repo = services_of(admin).repo
    family = repo.add_source("Family", "/family").id
    secret = repo.add_source("Admins only", "/secret", access=SourceAccess(None)).id
    n = 0

    def photos(
        count: int, start: datetime, step: timedelta, where: dict[str, float], source: int = family
    ) -> list[int]:
        nonlocal n
        made = []
        for i in range(count):
            n += 1
            asset_id = repo.add_asset(new_asset(n, start + i * step, **where), NOW)
            repo.add_asset_source(asset_id, source, f"{n}.jpg")
            made.append(asset_id)
        return made

    home = [
        i
        for w in range(40)
        for i in photos(
            2, datetime(2024, 1, 1, 18) + w * timedelta(7), timedelta(minutes=5), RENNES
        )
    ]
    trip = photos(9, datetime(2025, 7, 12, 10), timedelta(hours=1), MALO)
    trip += photos(1, datetime(2025, 7, 12, 20), timedelta(0), MALO, secret)
    repo.set_places([(i, Place("France", "Brittany", "Saint-Malo")) for i in trip])
    birthday = photos(8, datetime(2025, 3, 8, 14), timedelta(minutes=10), RENNES)
    repo.set_places([(i, Place("France", "Brittany", "Rennes")) for i in birthday])
    return {"home": home, "trip": trip, "birthday": birthday}


def test_suggestions_are_the_events_newest_first_named_from_facts(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    body = admin.get("/api/album-suggestions").json()
    trip, birthday = body
    assert trip | {"cover": trip["cover"]["id"]} == {
        "key": str(library["trip"][0]),
        "title": "Saint-Malo · 12 July 2025",
        "from": "2025-07-12",
        "to": "2025-07-12",
        "count": 10,
        "cover": library["trip"][5],
        "items": trip["items"],
    }
    assert [a["id"] for a in trip["items"]] == library["trip"][:4]
    assert birthday["title"] == "Rennes · 8 March 2025"


def test_a_member_is_suggested_only_photos_it_may_see(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    lea = add_user(admin, "lea")
    trip, _ = lea.get("/api/album-suggestions").json()
    assert trip["count"] == 9


def test_keep_makes_an_album_the_account_owns_and_the_suggestion_goes(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    lea = add_user(admin, "lea")
    key = str(library["trip"][0])

    kept = lea.post(f"/api/album-suggestions/{key}/keep")

    assert kept.status_code == 201, kept.text
    album = lea.get(f"/api/albums/{kept.json()['id']}").json()
    assert (album["title"], album["role"]) == ("Saint-Malo · 12 July 2025", "owner")
    assert [a["id"] for a in album["items"]] == library["trip"][:9]
    assert [s["key"] for s in lea.get("/api/album-suggestions").json()] == [
        str(library["birthday"][0])
    ]
    assert refusal(lea.post(f"/api/album-suggestions/{key}/keep"))[0] == 404
    assert len(admin.get("/api/album-suggestions").json()) == 2, "another account still sees it"


def test_discard_makes_nothing_and_is_remembered(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    key = str(library["birthday"][0])

    response = admin.post(f"/api/album-suggestions/{key}/discard")

    assert response.status_code == 204
    assert admin.get("/api/albums").json() == []
    assert [s["key"] for s in admin.get("/api/album-suggestions").json()] == [
        str(library["trip"][0])
    ]
    assert admin.post(f"/api/album-suggestions/{key}/discard").status_code == 404


def test_an_event_mostly_in_an_album_already_is_not_suggested(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    made = admin.post(
        "/api/albums", json={"title": "Birthday", "asset_ids": library["birthday"][:4]}
    )
    assert made.status_code == 201
    assert [s["title"] for s in admin.get("/api/album-suggestions").json()] == [
        "Saint-Malo · 12 July 2025"
    ]


def test_an_unknown_suggestion_is_not_found(admin: TestClient) -> None:
    assert refusal(admin.post("/api/album-suggestions/999/keep")) == (
        404,
        {"detail": "this suggestion is no longer there; the list may have changed"},
    )


def test_a_guest_who_cannot_make_albums_gets_no_suggestion(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    guest = add_user(admin, "sam", role="guest")
    assert guest.get("/api/album-suggestions").json() == []
    key = str(library["trip"][0])
    assert guest.post(f"/api/album-suggestions/{key}/keep").status_code == 403
    assert guest.post(f"/api/album-suggestions/{key}/discard").status_code == 403


# --- with the local AI switched on ------------------------------------------------------------

AI_ON = IntegrationSettings(
    ai_provider="ollama",
    ollama_base_url="http://127.0.0.1:9",  # nothing answers: no job runs in these tests
    ollama_caption_model="qwen3.5:4b",
    ollama_plan_model="qwen3.5:4b",
)


@pytest.fixture
def ai_admin(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path / "data", integrations=AI_ON))
    with TestClient(app, base_url=BASE) as client:
        made = client.post(
            "/api/setup", json={"username": "admin", "display_name": "C", "pin": PIN}
        )
        assert made.status_code == 201, made.text
        yield client


def _plan_jobs(client: TestClient) -> list[object]:
    return [j["payload"] for j in services_of(client).repo.list_jobs() if j["kind"] == PLAN_JOB]


def test_with_the_ai_off_no_plan_is_queued(
    admin: TestClient, library: dict[str, list[int]]
) -> None:
    admin.get("/api/album-suggestions")
    assert _plan_jobs(admin) == []


def test_with_the_ai_on_each_suggestion_gets_a_plan_queued_in_the_background(
    ai_admin: TestClient,
) -> None:
    library = _library(ai_admin)
    titles = [s["title"] for s in ai_admin.get("/api/album-suggestions").json()]
    assert titles == ["Saint-Malo · 12 July 2025", "Rennes · 8 March 2025"], "plain until planned"
    me = services_of(ai_admin).repo.list_users()[0].id
    assert _plan_jobs(ai_admin) == [
        {"user_id": me, "key": str(library["trip"][0])},
        {"user_id": me, "key": str(library["birthday"][0])},
    ]


def test_a_stored_plan_names_the_suggestion_and_the_album_kept_from_it(
    ai_admin: TestClient,
) -> None:
    library = _library(ai_admin)
    trip, key = library["trip"], str(library["trip"][0])
    plan = AlbumPlan("Kites over Saint-Malo", (PlanSection("Beach", tuple(trip), "single"),))
    services_of(ai_admin).repo.save_album_plan(key, photos_key(trip), "qwen3.5:4b", plan)

    shown = ai_admin.get("/api/album-suggestions").json()
    assert shown[0]["title"] == "Kites over Saint-Malo"
    kept = ai_admin.post(f"/api/album-suggestions/{key}/keep").json()
    assert ai_admin.get(f"/api/albums/{kept['id']}").json()["title"] == "Kites over Saint-Malo"


def test_a_member_who_sees_fewer_photos_of_the_event_gets_the_plain_title(
    ai_admin: TestClient,
) -> None:
    library = _library(ai_admin)
    trip, key = library["trip"], str(library["trip"][0])
    plan = AlbumPlan("Kites over Saint-Malo", (PlanSection("Beach", tuple(trip), "single"),))
    services_of(ai_admin).repo.save_album_plan(key, photos_key(trip), "qwen3.5:4b", plan)
    lea = add_user(ai_admin, "lea")
    assert lea.get("/api/album-suggestions").json()[0]["title"] == "Saint-Malo · 12 July 2025"
